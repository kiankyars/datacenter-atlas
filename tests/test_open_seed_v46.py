from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import socket
import stat
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v46.json"
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v46"
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v45.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v45"

DEFINITION_SHA256 = "b6021710df7211611975dd946ef0a14c974b29a782161af821512a3a167a2293"
MANIFEST_SHA256 = "85ebc71e3751d722da2b24ae36abd62de8733ff331883d686ea74f5c3987418d"
BASE_DEFINITION_SHA256 = (
    "c57e58d514fc69742b4dae5f8f1ea5244cc1f14aa1df6093d56abc8b779b6d13"
)
BASE_MANIFEST_SHA256 = (
    "275f5767c5f08208be7178126855ce5d3a77b217dbd53b2483450c46673b7a27"
)
RECORDED_AT = "2026-07-20T09:41:21Z"
MAX_INPUT_RETRIEVED_AT = "2026-07-20T09:05:11Z"
GOODMAN_PUBLISHED_AT = "2026-05-26"
GOODMAN_CAPACITY_AS_OF = "2026-03-31"
GOODMAN_EVIDENCE_ID = "e76fe169-8044-5df1-8943-837ec3c34e1b"
GOODMAN_EVIDENCE_KEY = (
    "goodman-q3-fy26-operational-update-pdf-captured-2026-07-20"
)
GOODMAN_PDF_SHA256 = (
    "713196902d9c92df2502874d5cfa44f86a2ac4de35022a76f33983dba8053227"
)
GOODMAN_SOURCE_FAMILY = "goodman_group_investor_presentations"

CODE_HASHES = {
    "datacenter_atlas/curated.py": "638d39c4199d4479106c365672ff9efb327f145ccf494bc92942ac6788c6cc12",
    "datacenter_atlas/epoch.py": "95f5513322aa77dbbece928954214bc931eb883656525f49f091959457735d31",
    "datacenter_atlas/open_seed_release.py": "674548884fa7271f4bef4ddaf2554bd8044289cb8d3d93aaa046fbe7d31038ab",
    "datacenter_atlas/publication_release.py": "a4d1aec6f0180003cdaea7bcfb89489aa391b888ca12b1ef5c730a3f28bbe510",
    "datacenter_atlas/release.py": "21ef472be6dad2112648bcd5e744e5f30a672bbd2a53386396ef2b0b50116056",
    "datacenter_atlas/release_contract_v4.py": "7faa3cca20cd724b75e2a574fccdaff21fd4db5073cb8f76683f4a973d821169",
    "scripts/build_open_seed.py": "0603c8025ea4dc77866c9cb913ffbe9d8c9db2dbfda87ecc446732258d6732a8",
    "scripts/validate_open_seed_release.py": "1159cdee91ae13c541164ab31009237a024362f3fc527b4a09709e7bfac09d81",
}

TEST_HASHES = {
    "tests/test_curated_goodman_q3_fy26.py": "31ccc99cb465fda786214a420d39459292bad86745d73a63503aba4ab1e3a35d",
    "tests/test_epoch.py": "9b60e4fd381799058ed39ca912d153102078e3f95e281c9cda86134952872c38",
    "tests/test_open_seed_v45.py": "4d44a1ebd0a5eb32707237c018b233760760c06cb0198ee1ba079b9a05498300",
    "tests/test_open_seed_release.py": "392b806639033497b7c9f43f577cce2e18864c2710fb9d6c393191d1f924e05e",
    "tests/test_release.py": "fbd8ee140aa611cf1750b9373d1063b4713f90b86e0d85f4bb77a6abaec28243",
    "tests/test_release_contract_v4.py": "7bc3c7d31576bd18597b1792f067abc018540e94b30ba960ef4e990828353ebd",
}

ADDED_INPUTS = {
    "sources/curated-official-2026-07-20-goodman-ams01-amsterdam.json": "86b5bab9cd778409410e5cd769cc7d7878f1d96d5ac4a8fe12471ae7ca43abd4",
    "sources/curated-official-2026-07-20-goodman-fra02-frankfurt.json": "f30db3b92de147265dfe281c307482f2679e57eecb7d436de8412179521408de",
    "sources/curated-official-2026-07-20-goodman-hkg09-kwai-chung.json": "e61f745ba1b4af4d095b84de81d31c4960a20137786589a949002640c864627c",
    "sources/curated-official-2026-07-20-goodman-hkg10-tsuen-wan.json": "a6d006f832c90cc98b457dc4213e4c44d1ae01b80315ab14a492bbc69b568c92",
    "sources/curated-official-2026-07-20-goodman-lax01-los-angeles.json": "5e79a2176b02b4be58d7531ef6a957e410ef28448e8dd7c8e9fc0f0d0839e9b7",
    "sources/curated-official-2026-07-20-goodman-par01-paris.json": "28179d0b0640362a2fa2405c8fb1564c408e3966fecac776267e091da1ea801a",
    "sources/curated-official-2026-07-20-goodman-par02-paris.json": "2ea8e966b737170e2e74ae829c89e61c9eacdc89fc980ceef344454834791e81",
    "sources/curated-official-2026-07-20-goodman-syd01-macquarie-park.json": "c09b538259662c918480f223912e622861cac5a25d0a6b946aa64d980e0e8561",
    "sources/curated-official-2026-07-20-goodman-ty005-tokyo.json": "7f73b491775f176a2ab1dbacad6842e1aca60b8797771d373bc6d48987f1b47d",
    "sources/curated-official-2026-07-20-goodman-ty006-tokyo.json": "76b5a70e873caa7993c18d2f546cfa993ea0ab1f110f22b5b4d7dde0c98715f0",
}

CAMPUS_TO_PROJECT = {
    "curated:goodman-ams01-amsterdam-data-centre-campus": (
        "curated:goodman-ams01-amsterdam-data-centre-campus:phase-1-current-development"
    ),
    "curated:goodman-fra02-frankfurt-data-centre-campus": (
        "curated:goodman-fra02-frankfurt-data-centre-campus:phase-1-current-development"
    ),
    "curated:goodman-hkg09-kwai-chung-data-centre": (
        "curated:goodman-hkg09-kwai-chung-data-centre:current-redevelopment"
    ),
    "curated:goodman-hkg10-tsuen-wan-data-centre": (
        "curated:goodman-hkg10-tsuen-wan-data-centre:current-redevelopment"
    ),
    "curated:goodman-lax01-los-angeles-program-anchor": (
        "curated:goodman-lax01-los-angeles-program-anchor:first-site-current-development"
    ),
    "curated:goodman-par01-paris-data-centre-campus": (
        "curated:goodman-par01-paris-data-centre-campus:phase-1-current-development"
    ),
    "curated:goodman-par02-paris-data-centre-campus": (
        "curated:goodman-par02-paris-data-centre-campus:phase-1-current-development"
    ),
    "curated:goodman-syd01-macquarie-park-data-centre": (
        "curated:goodman-syd01-macquarie-park-data-centre:current-single-building-development"
    ),
    "curated:goodman-ty005-tokyo-data-centre-campus": (
        "curated:goodman-ty005-tokyo-data-centre-campus:phase-1-current-development"
    ),
    "curated:goodman-ty006-tokyo-data-centre-site": (
        "curated:goodman-ty006-tokyo-data-centre-site:current-power-infrastructure-development"
    ),
}
CAMPUS_KEYS = set(CAMPUS_TO_PROJECT)
PROJECT_KEYS = set(CAMPUS_TO_PROJECT.values())

CAMPUS_OWNERS = {
    "curated:goodman-ams01-amsterdam-data-centre-campus": "Goodman European Data Centre Development Partnership I",
    "curated:goodman-fra02-frankfurt-data-centre-campus": "Goodman European Data Centre Development Partnership I",
    "curated:goodman-hkg09-kwai-chung-data-centre": "Goodman Hong Kong Data Centre Partnership",
    "curated:goodman-hkg10-tsuen-wan-data-centre": "Goodman Hong Kong Data Centre Partnership",
    "curated:goodman-lax01-los-angeles-program-anchor": "Goodman DataBank JV",
    "curated:goodman-par01-paris-data-centre-campus": "Goodman European Data Centre Development Partnership I",
    "curated:goodman-par02-paris-data-centre-campus": "Goodman European Data Centre Development Partnership I",
    "curated:goodman-syd01-macquarie-park-data-centre": "Goodman Group",
    "curated:goodman-ty005-tokyo-data-centre-campus": "Goodman Japan Development Partnership",
    "curated:goodman-ty006-tokyo-data-centre-site": "",
}

PROJECT_STATUSES = {
    CAMPUS_TO_PROJECT["curated:goodman-ams01-amsterdam-data-centre-campus"]: "mep_electrical",
    CAMPUS_TO_PROJECT["curated:goodman-fra02-frankfurt-data-centre-campus"]: "under_construction",
    CAMPUS_TO_PROJECT["curated:goodman-hkg09-kwai-chung-data-centre"]: "site_preparation",
    CAMPUS_TO_PROJECT["curated:goodman-hkg10-tsuen-wan-data-centre"]: "under_construction",
    CAMPUS_TO_PROJECT["curated:goodman-lax01-los-angeles-program-anchor"]: "mep_electrical",
    CAMPUS_TO_PROJECT["curated:goodman-par01-paris-data-centre-campus"]: "under_construction",
    CAMPUS_TO_PROJECT["curated:goodman-par02-paris-data-centre-campus"]: "mep_electrical",
    CAMPUS_TO_PROJECT["curated:goodman-syd01-macquarie-park-data-centre"]: "mep_electrical",
    CAMPUS_TO_PROJECT["curated:goodman-ty005-tokyo-data-centre-campus"]: "mep_electrical",
    CAMPUS_TO_PROJECT["curated:goodman-ty006-tokyo-data-centre-site"]: "under_construction",
}

# common, added count/hash, removed count/hash
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        583,
        20,
        "bde7c7ff5af2f2b9da3ac63b0f8ff2bc5380dd51ae1a4f27c3c573c7da4f8b5f",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "evidence.csv": (
        328,
        1,
        "75d002908a469e16f3dc45bb600a878c2e249c6dc51f1fae29d1ed94da237403",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "capacity_estimates.csv": (
        449,
        2,
        "bd5259fe10ed9fa66c1d39ec59e3e57ec8ced85fd06c1e7685b5accdbfae337a",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_pipeline.csv": (
        307,
        10,
        "36eee2229b053ed11e39b2ba5f23e6087ba92f005456edd2fb019a1eac52a5a9",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_source_signals.csv": (
        222,
        1,
        "7483d44fe3a2633808910f46a5517936982e073bc97fe85a0bef01dace5e81f5",
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


class OpenSeedV46Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        offline = AssertionError("v46 validation attempted network access")
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text

        def forbidden(path: Path) -> bool:
            name = path.name
            return (
                name.startswith("curated-official-2026-07-20-goodman-")
                and name.endswith("-v2.json")
            )

        def guarded_read_bytes(path: Path) -> bytes:
            if forbidden(path):
                raise AssertionError(f"v46 attempted excluded Goodman v2 input: {path}")
            return original_read_bytes(path)

        def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
            if forbidden(path):
                raise AssertionError(f"v46 attempted excluded Goodman v2 input: {path}")
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
        self.assertEqual(sha256(BASE_RELEASE / "manifest.json"), BASE_MANIFEST_SHA256)
        for collection in (CODE_HASHES, TEST_HASHES):
            for relative, expected in collection.items():
                path = ROOT / relative
                self.assertEqual(sha256(path), expected, relative)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644, relative)

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
        self.assertEqual(first["entities"], 603)
        self.assertEqual(first["entities_by_kind"], {"campus": 324, "project": 279})
        self.assertEqual(first["evidence_records"], 329)
        self.assertEqual(first["capacity_estimates"], 451)
        self.assertEqual(first["construction_pipeline_records"], 317)
        self.assertEqual(first["construction_source_signals"], 223)
        self.assertEqual(first["resolution_candidates"], 4)

        payloads = [DEFINITION.read_bytes(), *frozen.values()]
        excluded_goodman_v2 = re.compile(
            rb"curated-official-2026-07-20-goodman-[^\"\n]+-v2\.json"
        )
        self.assertFalse(
            any(excluded_goodman_v2.search(body) for body in payloads)
        )

    def test_definition_is_exact_v45_plus_ten_and_chronology_is_strict(self) -> None:
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
        self.assertEqual(len(base_pins), 277)
        self.assertEqual(len(current_pins), 287)
        self.assertEqual(
            {
                path: digest
                for path, digest in current_pins.items()
                if path not in base_pins
            },
            ADDED_INPUTS,
        )
        self.assertFalse(set(base_pins) - set(current_pins))
        self.assertFalse(
            {
                path
                for path in base_pins
                if base_pins[path] != current_pins[path]
            }
        )
        ordered = [record["path"] for record in current["curated_inputs"]]
        self.assertEqual(ordered, sorted(set(ordered)))
        self.assertFalse(
            any(
                path.startswith("sources/curated-official-2026-07-20-goodman-")
                and path.endswith("-v2.json")
                for path in current_pins
            )
        )

        retrieved_at: list[str] = [current["epoch_capture"]["retrieved_at"]]
        for relative, expected in current_pins.items():
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertFalse(path.is_symlink(), relative)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644, relative)
            self.assertEqual(sha256(path), expected, relative)
            document = json.loads(path.read_text(encoding="utf-8"))
            timestamps = [record["retrieved_at"] for record in document.get("evidence", [])]
            if relative in ADDED_INPUTS:
                self.assertEqual(set(timestamps), {MAX_INPUT_RETRIEVED_AT})
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
        self.assertEqual(current["build"], {"as_of": "2026-07-20", "recorded_at": RECORDED_AT})
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v46")
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
        expected_release = {key: value for key, value in manifest.items() if key != "files"}
        expected_release["manifest_sha256"] = hashlib.sha256(manifest_raw).hexdigest()
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

    def test_exact_v45_to_v46_additive_release_delta(self) -> None:
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
        self.assertEqual(
            set(after_entities) - set(before_entities), CAMPUS_KEYS | PROJECT_KEYS
        )
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

        before_evidence = by_key(BASE_RELEASE / "evidence.csv", "evidence_id")
        after_evidence = by_key(RELEASE / "evidence.csv", "evidence_id")
        self.assertEqual(set(after_evidence) - set(before_evidence), {GOODMAN_EVIDENCE_ID})
        self.assertFalse(set(before_evidence) - set(after_evidence))
        self.assertFalse(
            {
                key
                for key in set(before_evidence) & set(after_evidence)
                if before_evidence[key] != after_evidence[key]
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
        self.assertEqual(set(after_signals) - set(before_signals), {GOODMAN_EVIDENCE_ID})
        self.assertFalse(set(before_signals) - set(after_signals))
        self.assertFalse(
            {
                key
                for key in set(before_signals) & set(after_signals)
                if before_signals[key] != after_signals[key]
            }
        )

        before_sources = json.loads(
            (BASE_RELEASE / "source_inputs.json").read_text(encoding="utf-8")
        )["sources"]
        after_sources = json.loads(
            (RELEASE / "source_inputs.json").read_text(encoding="utf-8")
        )["sources"]
        packed_before = {canonical_hash(record): record for record in before_sources}
        packed_after = {canonical_hash(record): record for record in after_sources}
        self.assertEqual(len(packed_before), 255)
        self.assertEqual(len(packed_after), 256)
        self.assertFalse(set(packed_before) - set(packed_after))
        added_sources = [packed_after[key] for key in set(packed_after) - set(packed_before)]
        self.assertEqual(len(added_sources), 1)
        self.assertEqual(
            added_sources[0],
            {
                "license": "all-rights-reserved",
                "provenance": {
                    "content_hash": GOODMAN_PDF_SHA256,
                    "content_hash_scope": "SHA-256 of the exact 9358661-byte official PDF response body",
                    "content_hash_verification": "fetched_bytes_sha256",
                    "curated_record_key": GOODMAN_EVIDENCE_KEY,
                },
                "publisher": "Goodman Group",
                "retrieved_at": MAX_INPUT_RETRIEVED_AT,
                "source_family": GOODMAN_SOURCE_FAMILY,
                "source_url": "https://www.goodman.com/-/media/project/goodman/global/files/investor-centre/gmg-goodman-group/announcements/asx-announcements/2026/q3-fy26-operational-update.pdf?rev=eb06cc22996840e1830b4085fdc24597",
            },
        )

    def test_goodman_semantics_are_exact_and_create_no_inferred_claims(self) -> None:
        before_entities = by_key(BASE_RELEASE / "entities.csv", "stable_key")
        after_entities = by_key(RELEASE / "entities.csv", "stable_key")
        added = {
            key: after_entities[key]
            for key in set(after_entities) - set(before_entities)
        }
        self.assertEqual(Counter(row["entity_kind"] for row in added.values()), {"campus": 10, "project": 10})
        self.assertEqual(
            Counter(row["status"] for row in added.values()),
            {"": 10, "mep_electrical": 5, "under_construction": 4, "site_preparation": 1},
        )

        for key, row in added.items():
            self.assertEqual(row["snapshot_as_of"], GOODMAN_PUBLISHED_AT)
            self.assertEqual(row["snapshot_evidence_id"], GOODMAN_EVIDENCE_ID)
            self.assertEqual(row["source_retrieved_at"], MAX_INPUT_RETRIEVED_AT)
            self.assertEqual(row["latitude"], "")
            self.assertEqual(row["longitude"], "")
            self.assertEqual(row["geometry_json"], "null")
            self.assertEqual(row["operating_model"], "")
            self.assertEqual(row["operating_model_evidence_id"], "")
            self.assertEqual(row["workloads_json"], "[]")
            self.assertEqual(row["operator"], "")
            self.assertEqual(row["users"], "")
            self.assertEqual(row["tenants"], "")
            self.assertEqual(row["customers"], "")
            if key in CAMPUS_KEYS:
                self.assertEqual(row["status"], "")
                self.assertEqual(row["status_evidence_id"], "")
                self.assertEqual(row["owner"], CAMPUS_OWNERS[key])
                self.assertEqual(row["capacity_estimates_json"], "[]")
            else:
                self.assertEqual(row["owner"], "")
                self.assertEqual(row["status"], PROJECT_STATUSES[key])
                self.assertEqual(row["status_as_of"], GOODMAN_PUBLISHED_AT)
                self.assertEqual(row["status_method"], "authoritative_physical_status_update")
                self.assertEqual(row["status_evidence_id"], GOODMAN_EVIDENCE_ID)

        ty006_project = CAMPUS_TO_PROJECT[
            "curated:goodman-ty006-tokyo-data-centre-site"
        ]
        self.assertNotEqual(added[ty006_project]["capacity_estimates_json"], "[]")
        for key in PROJECT_KEYS - {ty006_project}:
            self.assertEqual(added[key]["capacity_estimates_json"], "[]")

        evidence = by_key(RELEASE / "evidence.csv", "evidence_id")[GOODMAN_EVIDENCE_ID]
        self.assertEqual(evidence["source_family"], GOODMAN_SOURCE_FAMILY)
        self.assertEqual(evidence["published_at"], GOODMAN_PUBLISHED_AT)
        self.assertEqual(evidence["retrieved_at"], MAX_INPUT_RETRIEVED_AT)
        self.assertEqual(evidence["content_hash"], GOODMAN_PDF_SHA256)

        signal = by_key(
            RELEASE / "construction_source_signals.csv",
            "source_observation_evidence_id",
        )[GOODMAN_EVIDENCE_ID]
        self.assertEqual(signal["affected_entity_count"], "10")
        affected = json.loads(signal["affected_entities_json"])
        self.assertEqual({record["stable_key"] for record in affected}, PROJECT_KEYS)
        self.assertTrue(all(record["status_as_of"] == GOODMAN_PUBLISHED_AT for record in affected))

        before_capacity = row_counter(BASE_RELEASE / "capacity_estimates.csv")
        after_capacity = row_counter(RELEASE / "capacity_estimates.csv")
        capacities = normalized_counter_rows(after_capacity - before_capacity)
        self.assertEqual(
            {(row["metric"], row["base"]) for row in capacities},
            {("gross_facility_mw", "50.0"), ("critical_it_mw", "33.0")},
        )
        for row in capacities:
            self.assertEqual(row["name"], "Goodman TY006 Current Power Infrastructure Development")
            self.assertEqual(row["stage"], "planned")
            self.assertEqual(row["unit"], "MW")
            self.assertEqual(row["method"], "reported")
            self.assertEqual(row["as_of_date"], GOODMAN_CAPACITY_AS_OF)
            self.assertEqual(row["target_date"], "")
            self.assertEqual(row["evidence_id"], GOODMAN_EVIDENCE_ID)
            self.assertIn("not additive", row["notes"])
            self.assertIn("not current load", row["notes"])

        documents = {
            relative: json.loads((ROOT / relative).read_text(encoding="utf-8"))
            for relative in ADDED_INPUTS
        }
        evidence_documents = [document["evidence"][0] for document in documents.values()]
        self.assertTrue(all(record == evidence_documents[0] for record in evidence_documents))
        for document in documents.values():
            self.assertEqual(document["campus"]["as_of_date"], GOODMAN_PUBLISHED_AT)
            self.assertEqual(document["project"]["as_of_date"], GOODMAN_PUBLISHED_AT)
            self.assertEqual(document["project"]["roles"], {})
            self.assertIsNone(document["campus"]["coordinates"])
            self.assertIsNone(document["project"]["coordinates"])
            self.assertIsNone(document["campus"]["geometry"])
            self.assertIsNone(document["project"]["geometry"])
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            self.assertEqual(document["lifecycle"][0]["as_of_date"], GOODMAN_PUBLISHED_AT)
            self.assertEqual(
                document["lifecycle"][0]["value"],
                PROJECT_STATUSES[document["project"]["stable_key"]],
            )

        lax = documents[
            "sources/curated-official-2026-07-20-goodman-lax01-los-angeles.json"
        ]
        self.assertEqual(lax["capacities"], [])
        self.assertIn("program-anchor", lax["campus"]["stable_key"])
        self.assertEqual(lax["campus"]["address"], "Los Angeles metro, United States")
        metadata = lax["evidence"][0]["metadata"]
        self.assertEqual(
            metadata["page_6_column_headings_as_reported"],
            [
                "FY26 PROJECTED DC WIP PROJECTS (MW)",
                ">FY26 SECURED PIPELINE ON CAMPUS (MW)",
                "TOTAL (MW)",
            ],
        )
        self.assertEqual(
            metadata["page_6_dc_wip_pipeline_table_totals_as_reported_mw"],
            {
                "fy26_projected_dc_wip_projects_mw": 497,
                "greater_than_fy26_secured_pipeline_on_campus_mw": 1332,
                "total_mw": 1829,
            },
        )
        lax_row = next(
            row
            for row in metadata["page_6_dc_wip_pipeline_table_as_reported"]
            if row["facility_code"] == "LAX01"
        )
        self.assertEqual(lax_row["reported_program_site_count"], 3)
        self.assertEqual(lax_row["first_site_resolution"], "unresolved")
        self.assertIn("non-site program anchor", metadata["lax01_program_anchor_guardrail"])
        self.assertIn("non-additive", metadata["ty006_capacity_scope"])
        self.assertIn("no site-level current electrical load", metadata["energy_guardrail"])

        all_keys = set(after_entities)
        self.assertFalse(any("mad01" in key.lower() for key in all_keys - set(before_entities)))
        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["capacity_estimates_current"], 451)
        self.assertNotIn("capacity_base_totals", summary)
        self.assertFalse(summary["capacity_aggregation"]["base_totals_published"])
        self.assertFalse(summary["capacity_aggregation"]["cross_entity_sum_valid"])


if __name__ == "__main__":
    unittest.main()
