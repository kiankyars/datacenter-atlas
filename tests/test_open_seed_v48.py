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
DEFINITION = ROOT / "sources/open-seed-2026-07-20-v48.json"
RELEASE = ROOT / "releases/2026-07-20-open-seed-v48"
BASE_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v46.json"
BASE_RELEASE = ROOT / "releases/2026-07-20-open-seed-v46"

DEFINITION_SHA256 = (
    "7d94cc5359a326f2ffaf00b28816a8d1751a25079cfd0264115246fdbbe78f89"
)
MANIFEST_SHA256 = (
    "8e708671fd88ca2b4d9c106bda6a692e06e11f2ab1a6b72e31342277e300eee8"
)
BASE_DEFINITION_SHA256 = (
    "b6021710df7211611975dd946ef0a14c974b29a782161af821512a3a167a2293"
)
BASE_MANIFEST_SHA256 = (
    "85ebc71e3751d722da2b24ae36abd62de8733ff331883d686ea74f5c3987418d"
)
RECORDED_AT = "2026-07-20T11:00:00Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T09:25:15Z"
TREE_SHA256 = "0904b17b343548075a6dec689267adb2767ca525b9b7d8fcb5300de07aa1fd1c"

CODE_HASHES = {
    "datacenter_atlas/curated.py": (
        "638d39c4199d4479106c365672ff9efb327f145ccf494bc92942ac6788c6cc12"
    ),
    "datacenter_atlas/epoch.py": (
        "95f5513322aa77dbbece928954214bc931eb883656525f49f091959457735d31"
    ),
    "datacenter_atlas/open_seed_release.py": (
        "674548884fa7271f4bef4ddaf2554bd8044289cb8d3d93aaa046fbe7d31038ab"
    ),
    "datacenter_atlas/publication_release.py": (
        "a4d1aec6f0180003cdaea7bcfb89489aa391b888ca12b1ef5c730a3f28bbe510"
    ),
    "datacenter_atlas/release.py": (
        "21ef472be6dad2112648bcd5e744e5f30a672bbd2a53386396ef2b0b50116056"
    ),
    "datacenter_atlas/release_contract_v4.py": (
        "7faa3cca20cd724b75e2a574fccdaff21fd4db5073cb8f76683f4a973d821169"
    ),
    "scripts/build_open_seed_v48.py": (
        "593807e719a7fc50e552924c7a48cd7aecad9bfa022b94a83f5eb678a98599ac"
    ),
    "scripts/validate_open_seed_release.py": (
        "1159cdee91ae13c541164ab31009237a024362f3fc527b4a09709e7bfac09d81"
    ),
}

ADDED_INPUTS = {
    "sources/curated-official-2026-07-20-alto-sp01-granada.json": (
        "5e2f4e431b877d403d3f34d1d5de689450cfa58d1670c9e8b038f39f21d5cc80"
    ),
    "sources/curated-official-2026-07-20-digipower-columbiana-shell-v2.json": (
        "a137bd6356ead2052ad160aa50c7ab27d7871f4b2552dba276ffa86949f46ccd"
    ),
    "sources/curated-official-2026-07-20-galaxy-helios-phase2.json": (
        "5463da008a588bb9993310ee13ca82da039435cf5f3815c574d3ac0ee576f57f"
    ),
    "sources/curated-official-2026-07-20-hut8-beacon-point.json": (
        "b6209a4c9ebaefe562b541834c9d89a19482cfd79a4cf7de156df848ed7834f1"
    ),
    "sources/curated-official-2026-07-20-kasi-los1-commissioning.json": (
        "caaddbfbc641c00c87c7b7fcfb29c5f2af5df8f7ca541dcff6d94294e42afd01"
    ),
}

GOODMAN_V1_PATHS = {
    f"sources/curated-official-2026-07-20-goodman-{slug}.json"
    for slug in (
        "ams01-amsterdam",
        "fra02-frankfurt",
        "hkg09-kwai-chung",
        "hkg10-tsuen-wan",
        "lax01-los-angeles",
        "par01-paris",
        "par02-paris",
        "syd01-macquarie-park",
        "ty005-tokyo",
        "ty006-tokyo",
    )
}
VNET_SLUGS = (
    "e-js03b",
    "n-hb02",
    "n-hb03",
    "n-hb04",
    "n-or01",
    "n-or02a",
    "n-or02b",
    "n-or03",
)
VNET_V1_PATHS = {
    f"sources/curated-official-2026-07-20-vnet-{slug}.json"
    for slug in VNET_SLUGS
}
GOODMAN_V2_PATHS = {
    path.removesuffix(".json") + "-v2.json" for path in GOODMAN_V1_PATHS
}
VNET_V2_PATHS = {
    path.removesuffix(".json") + "-v2.json" for path in VNET_V1_PATHS
}
EXCLUDED_SOURCE_PATHS = (
    GOODMAN_V2_PATHS
    | VNET_V2_PATHS
    | {
        "sources/curated-official-2026-07-20-digipower-columbiana-shell.json",
        "sources/curated-official-2026-07-20-stack-stafford-first-topout.json",
    }
)
FORBIDDEN_PATH_FRAGMENTS = tuple(EXCLUDED_SOURCE_PATHS) + (
    "sources/open-seed-2026-07-20-v47.json",
    "releases/2026-07-20-open-seed-v47",
)
FORBIDDEN_PAYLOAD_MARKERS = tuple(
    marker.encode("ascii")
    for marker in (
        *EXCLUDED_SOURCE_PATHS,
        "sources/open-seed-2026-07-20-v47.json",
        "releases/2026-07-20-open-seed-v47",
        "2026-07-20-open-seed-v47",
        "af6d130e0139495d0569115614d8112b56b7a16a5cc158efdcf24115fc076db2",
        "c0e228ed27e28830b466592bfc9a937f3c0d684be4fb97c7a20ac78e1c8a22a1",
    )
)

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (
        3087,
        "d4e3d56b0ea5e9dc9fe54d9199d95cc9e0205e69fc20af7805d5b04f3279aaf5",
    ),
    "README.md": (
        2625,
        "647aa5f70b5cc1cc6376e056612af945b49dc6ba0149d5a5ac354b349b597cf5",
    ),
    "atlas.geojson": (
        2_181_540,
        "e08a9c0994e0a9d22f3d00277327e0c0641df29b7b7edae2eba7451149040a51",
    ),
    "capacity_estimates.csv": (
        213_226,
        "15e6584eab5dfe64a9fac931bd6ca6cb10566e106e48af32fc6c702cfe18e16a",
    ),
    "construction_pipeline.csv": (
        425_143,
        "fab652f16d5943b055c91743c1232299a5ef8fa6df89777f1daaaa6d365fbb13",
    ),
    "construction_source_signals.csv": (
        253_217,
        "67e554959cf9e927e2ebcb10e7233416f2561ea6d573072be45043d3a8dc38f9",
    ),
    "entities.csv": (
        685_068,
        "436973f9c262c4b0d9ae2c32224fd45ee7474d4e3715de208c909d4869f8efee",
    ),
    "evidence.csv": (
        129_450,
        "1b070bf38525a44773d34db59cd0d157cb57244f22e50daa2ea1fa87946592e2",
    ),
    "manifest.json": (7970, MANIFEST_SHA256),
    "resolution_candidates.csv": (
        4011,
        "4fe2af9c7ae416221e91e824d069e846a9346ae9be82987baff83ebab6beb897",
    ),
    "resolution_candidates.json": (
        5874,
        "81f23af164d1d0eac5de421d7b217ad2481280dbeefebc7e01c2a1dbef96b1d0",
    ),
    "source_inputs.json": (
        188_392,
        "6926569d32b7f62009b1a79dc45eed4dcaa129181291568c9e4d49d281177424",
    ),
    "summary.json": (
        2805,
        "663868f17a0e17c082a9584f5795288d64d3e655154fadb70d385990b138acff",
    ),
}

# common count, added count/hash, removed count/hash
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        603,
        10,
        "017b9ceb487d96b93c5f87fbee5c08f11344b37b1c7b623ecd179348a418acb5",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "evidence.csv": (
        329,
        7,
        "08f9387a2aad7a6e39fd39e19c1447bfeff23c58baa6a5aa6316511a150bcf3f",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "capacity_estimates.csv": (
        451,
        5,
        "135bfd8ddd31f21e2942a3c72eec4ae109ad12f092bf2add6099e6cef533c076",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_pipeline.csv": (
        317,
        5,
        "fb456d14c747c506b6fc76c12f88e53eb78c1b832806d40abbcd196948607fda",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_source_signals.csv": (
        223,
        5,
        "d24ce227c7937ec0eb7aa165b9166fd11f7dbd144b1d81e680eb3fd493e866ca",
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

PROJECT_STATUS = {
    "curated:alto-sp01-granada-data-center-campus:phase-1-10mw-critical-it": (
        "under_construction"
    ),
    "curated:digipowerx-columbiana-ai-data-center-campus:purpose-built-flagship-vertical-build": (
        "shell"
    ),
    "curated:galaxy-helios-data-center-campus:phase-2-260mw-critical-it-build": (
        "under_construction"
    ),
    "curated:hut8-beacon-point-ai-data-center-campus:first-phase-352mw-critical-it-lease": (
        "announced"
    ),
    "curated:kasi-lekki-data-centre-campus:los1-first-building": "commissioning",
}
CAMPUS_KEYS = {key.rsplit(":", 1)[0] for key in PROJECT_STATUS}
ADDED_ENTITY_KEYS = CAMPUS_KEYS | set(PROJECT_STATUS)
ADDED_EVIDENCE_IDS = {
    "25d30d41-6ee8-521c-a8d5-5fc372370ebb",
    "2943a4a8-ef4a-5f43-9f4d-5be67ac22a5e",
    "685725e9-30ad-549a-ac10-7b2034a50b12",
    "8c104356-5de7-5156-9a00-2996e59f07af",
    "a17991df-ef8b-57e2-87fd-aea9770b9b44",
    "afb9a2fa-7d6d-57ef-8cbb-ef73595ed596",
    "f9be097a-99d8-5f60-9672-146a49d37f53",
}
SIGNAL_EVIDENCE_IDS = {
    "25d30d41-6ee8-521c-a8d5-5fc372370ebb",
    "2943a4a8-ef4a-5f43-9f4d-5be67ac22a5e",
    "685725e9-30ad-549a-ac10-7b2034a50b12",
    "8c104356-5de7-5156-9a00-2996e59f07af",
    "f9be097a-99d8-5f60-9672-146a49d37f53",
}
EXPECTED_CAPACITIES = {
    (
        "curated:alto-sp01-granada-data-center-campus:phase-1-10mw-critical-it",
        "critical_it_mw",
        "planned",
        "10.0",
        "2026-07-09",
    ),
    (
        "curated:galaxy-helios-data-center-campus:phase-2-260mw-critical-it-build",
        "critical_it_mw",
        "contracted",
        "260.0",
        "2026-07-06",
    ),
    (
        "curated:hut8-beacon-point-ai-data-center-campus",
        "grid_connection_mw",
        "contracted",
        "1000.0",
        "2026-05-06",
    ),
    (
        "curated:hut8-beacon-point-ai-data-center-campus:first-phase-352mw-critical-it-lease",
        "critical_it_mw",
        "contracted",
        "352.0",
        "2026-05-06",
    ),
    (
        "curated:kasi-lekki-data-centre-campus",
        "critical_it_mw",
        "planned",
        "100.0",
        "2026-05-19",
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


class OpenSeedV48Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        offline = AssertionError("v48 validation attempted network access")
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text

        def forbidden(path: Path) -> bool:
            rendered = path.resolve().as_posix()
            return any(marker in rendered for marker in FORBIDDEN_PATH_FRAGMENTS)

        def guarded_read_bytes(path: Path) -> bytes:
            if forbidden(path):
                raise AssertionError(f"v48 attempted forbidden input access: {path}")
            return original_read_bytes(path)

        def guarded_read_text(
            path: Path, *args: object, **kwargs: object
        ) -> str:
            if forbidden(path):
                raise AssertionError(f"v48 attempted forbidden input access: {path}")
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

    def test_exact_pins_tree_double_offline_reproduction_and_frozen_bundle(
        self,
    ) -> None:
        self.assertEqual(sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(sha256(RELEASE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(sha256(BASE_DEFINITION), BASE_DEFINITION_SHA256)
        self.assertEqual(
            sha256(BASE_RELEASE / "manifest.json"), BASE_MANIFEST_SHA256
        )
        for relative, expected in CODE_HASHES.items():
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
        self.assertEqual({path.name for path in entries}, set(RELEASE_FILE_PINS))
        tree: dict[str, dict[str, object]] = {}
        for path in entries:
            expected_bytes, expected_hash = RELEASE_FILE_PINS[path.name]
            self.assertTrue(path.is_file(), path.name)
            self.assertFalse(path.is_symlink(), path.name)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path.name)
            self.assertEqual(path.stat().st_size, expected_bytes, path.name)
            self.assertEqual(sha256(path), expected_hash, path.name)
            tree[path.name] = {"bytes": expected_bytes, "sha256": expected_hash}
        self.assertEqual(canonical_hash(tree), TREE_SHA256)

        frozen = {path.name: path.read_bytes() for path in entries}
        first = self._validate_offline()
        second = self._validate_offline()
        self.assertEqual(first, second)
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        self.assertEqual(first["publication_contract_version"], 4)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 613)
        self.assertEqual(first["entities_by_kind"], {"campus": 329, "project": 284})
        self.assertEqual(first["evidence_records"], 336)
        self.assertEqual(first["capacity_estimates"], 456)
        self.assertEqual(first["construction_pipeline_records"], 322)
        self.assertEqual(first["construction_source_signals"], 228)
        self.assertEqual(first["resolution_candidates"], 4)
        self.assertEqual(len(first["source_families"]), 168)

        payloads = [DEFINITION.read_bytes(), *frozen.values()]
        for marker in FORBIDDEN_PAYLOAD_MARKERS:
            self.assertFalse(any(marker in payload for payload in payloads), marker)

    def test_definition_is_exact_v46_plus_five_and_strictly_chronological(
        self,
    ) -> None:
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
        self.assertEqual(len(base_pins), 287)
        self.assertEqual(len(current_pins), 292)
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
        self.assertTrue(GOODMAN_V1_PATHS <= set(current_pins))
        self.assertTrue(VNET_V1_PATHS <= set(current_pins))
        self.assertTrue(EXCLUDED_SOURCE_PATHS.isdisjoint(current_pins))
        for path in GOODMAN_V1_PATHS | VNET_V1_PATHS:
            self.assertEqual(current_pins[path], base_pins[path], path)

        retrieved_at = [current["epoch_capture"]["retrieved_at"]]
        for relative, expected in current_pins.items():
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertFalse(path.is_symlink(), relative)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644, relative)
            self.assertEqual(sha256(path), expected, relative)
            document = json.loads(path.read_text(encoding="utf-8"))
            timestamps = [row["retrieved_at"] for row in document.get("evidence", [])]
            self.assertEqual(len(set(timestamps)), 1, relative)
            retrieved_at.extend(timestamps)
        self.assertEqual(max(retrieved_at), MAX_SELECTED_RETRIEVED_AT)
        cutoff = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
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
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v48")
        for key in (
            "epoch_capture",
            "expected_epoch_result",
            "publication_contract_version",
            "schema_version",
            "scope",
        ):
            self.assertEqual(current[key], base[key], key)
        self.assertEqual(
            current["scope"],
            {
                "commercial_census_parity_claimed": False,
                "epoch_selected_site_count_is_global_census": False,
                "orphan_timeline_imported": False,
                "source_scoped_estimates_only": True,
            },
        )

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
                "entities_total": 613,
                "evidence_total": 391,
                "projects_total": 284,
            },
        )

    def test_exact_v46_to_v48_additive_release_delta(self) -> None:
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
        self.assertEqual(set(after_entities) - set(before_entities), ADDED_ENTITY_KEYS)
        self.assertFalse(set(before_entities) - set(after_entities))
        self.assertFalse(
            {
                key
                for key in set(before_entities) & set(after_entities)
                if before_entities[key] != after_entities[key]
            }
        )

        before_pipeline = by_key(
            BASE_RELEASE / "construction_pipeline.csv", "stable_key"
        )
        after_pipeline = by_key(RELEASE / "construction_pipeline.csv", "stable_key")
        self.assertEqual(
            set(after_pipeline) - set(before_pipeline), set(PROJECT_STATUS)
        )
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
        self.assertEqual(
            set(after_evidence) - set(before_evidence), ADDED_EVIDENCE_IDS
        )
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
        self.assertEqual(
            set(after_signals) - set(before_signals), SIGNAL_EVIDENCE_IDS
        )
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
        packed_before = {canonical_hash(row): row for row in before_sources}
        packed_after = {canonical_hash(row): row for row in after_sources}
        self.assertEqual(len(packed_before), 256)
        self.assertEqual(len(packed_after), 263)
        self.assertFalse(set(packed_before) - set(packed_after))
        added_sources = [
            packed_after[key] for key in set(packed_after) - set(packed_before)
        ]
        added_sources.sort(
            key=lambda row: json.dumps(
                row,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
        )
        self.assertEqual(len(added_sources), 7)
        self.assertEqual(
            canonical_hash(added_sources),
            "8aeca6aee8dff3146df7bb82d3dbdb6a656577fa913c44f42cfac2697cb6ec87",
        )

    def test_selected_semantics_keep_status_and_power_scopes_typed(self) -> None:
        entities = by_key(RELEASE / "entities.csv", "stable_key")
        for key in CAMPUS_KEYS:
            self.assertEqual(entities[key]["status"], "", key)
            self.assertEqual(entities[key]["status_evidence_id"], "", key)
        for key, expected_status in PROJECT_STATUS.items():
            self.assertEqual(entities[key]["status"], expected_status, key)
        for key in ADDED_ENTITY_KEYS:
            self.assertEqual(entities[key]["latitude"], "", key)
            self.assertEqual(entities[key]["longitude"], "", key)
            self.assertEqual(entities[key]["geometry_json"], "null", key)

        digipower = (
            "curated:digipowerx-columbiana-ai-data-center-campus:"
            "purpose-built-flagship-vertical-build"
        )
        self.assertEqual(entities[digipower]["status"], "shell")
        self.assertEqual(entities[digipower]["operating_model"], "colocation")
        self.assertEqual(entities[digipower]["capacity_estimates_json"], "[]")
        self.assertNotIn("operational", entities[digipower]["status"])

        entity_keys = {
            row["entity_id"]: row["stable_key"]
            for row in rows(RELEASE / "entities.csv")
        }
        before_capacity = row_counter(BASE_RELEASE / "capacity_estimates.csv")
        after_capacity = row_counter(RELEASE / "capacity_estimates.csv")
        added_capacity = [
            dict(packed) for packed in (after_capacity - before_capacity).elements()
        ]
        self.assertEqual(
            {
                (
                    entity_keys[row["entity_id"]],
                    row["metric"],
                    row["stage"],
                    row["base"],
                    row["as_of_date"],
                )
                for row in added_capacity
            },
            EXPECTED_CAPACITIES,
        )
        self.assertTrue(
            all(row["metric"] in {"critical_it_mw", "grid_connection_mw"} for row in added_capacity)
        )
        self.assertTrue(
            all(
                "current load" in row["notes"].lower()
                and "generation" in row["notes"].lower()
                and "energy" in row["notes"].lower()
                for row in added_capacity
            )
        )

        digipower_document = json.loads(
            (ROOT / next(path for path in ADDED_INPUTS if "digipower" in path)).read_text(
                encoding="utf-8"
            )
        )
        digipower_metadata = digipower_document["evidence"][0]["metadata"]
        self.assertEqual(
            digipower_metadata["reported_physical_work"],
            [
                "project is transitioning from site and civil work to vertical construction",
                "building shell being erected",
                "vertical construction underway",
            ],
        )
        self.assertIn("create no normalized capacity", digipower_metadata["capacity_guardrail"])
        self.assertIn("does not make", digipower_metadata["operational_module_guardrail"])

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["capacity_estimates_current"], 456)
        self.assertNotIn("capacity_base_totals", summary)
        self.assertFalse(summary["capacity_aggregation"]["base_totals_published"])
        self.assertFalse(summary["capacity_aggregation"]["cross_entity_sum_valid"])
        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("does not publish aggregate capacity totals", readme)
        self.assertIn("not a global census", readme)
        self.assertIn("not a claim of parity with SemiAnalysis", readme)


if __name__ == "__main__":
    unittest.main()
