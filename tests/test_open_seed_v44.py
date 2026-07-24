from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import csv
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.open_seed_release import validate_open_seed_release


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v44.json"
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v44"
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v43.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v43"

DEFINITION_SHA256 = "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312"
MANIFEST_SHA256 = "908e1bc368d7c18d004303e5638a0814dc8ed2294a30175caec12b5e0837bdf9"
BASE_DEFINITION_SHA256 = (
    "3b789babfbaaad54166bb7b94305c24258644bec239dd76dcf19186fdd56d6fa"
)
BASE_MANIFEST_SHA256 = (
    "32f0b99553f925fdd47250c9a8382e81fdfc82a92a66b12793864ddf9a196537"
)
RECORDED_AT = "2026-07-20T07:47:00Z"
MAX_INPUT_RETRIEVED_AT = "2026-07-20T07:24:40Z"

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
    "tests/test_curated_ascenty_sumare3_20260720.py": "856d8e97bddb19c53879f8b94ad60dd230698276bf0042dde12e20db8789427b",
    "tests/test_curated_global_gap_tranche_20260720.py": "831781a3baf4beb76e1537d4f45cce102871365f7d5a7e83bbb85efa8ab96ac3",
    "tests/test_curated_menlo_imdc_20260720.py": "f25f2cce1de86c3773cee25c28729fd932e66d7688411d97e7515637b2694b3f",
    "tests/test_curated_pdg_jh1_johor_phases_4_5.py": "53909918da67c04e87b1f8af009e9da8925e5640c4fbc8d218ba4957fb01d526",
    "tests/test_curated_racks_central_johor.py": "e016ec764dbf0a26154754fef6cc2501a2b9014a4db1e54e33028931bc896311",
    "tests/test_curated_stt_navi_mumbai_23_20260720.py": "954179d38c529dff65876a1dbcf0b86ef666c505950c262d25a84e3930eed443",
    "tests/test_curated_stt_palava_20260720.py": "ba5cec027f1656af9f1bbe2a397f028ecf152d3693e91439ab97e162665bb954",
    "tests/test_open_seed_release.py": "392b806639033497b7c9f43f577cce2e18864c2710fb9d6c393191d1f924e05e",
    "tests/test_open_seed_v43.py": "005a75ed8ddbd3a2375dcfa65fc9f21f0d93c8aabe6f58bc314983c9850a8d7f",
    "tests/test_release.py": "fbd8ee140aa611cf1750b9373d1063b4713f90b86e0d85f4bb77a6abaec28243",
    "tests/test_release_contract_v4.py": "7bc3c7d31576bd18597b1792f067abc018540e94b30ba960ef4e990828353ebd",
}

ADDED_INPUTS = {
    "sources/curated-official-2026-07-20-ascenty-sumare-3.json": "000f59a93f94dc9a3e3dc87cb357506e4df036f12eaf42ebbd009ca1e766626d",
    "sources/curated-official-2026-07-20-crane-pdx-current-development.json": "46bf6c33739134c8653827d47eed2a7b4cb8f068a594c6c5b7cd5f7740d5c6b1",
    "sources/curated-official-2026-07-20-digital-halo-jhb1-johor-topout.json": "dfac2adbae97ce67418a1818064dad510e8af1b5b0b316af38df648f32f5796b",
    "sources/curated-official-2026-07-20-iron-mountain-chn1-chennai-topout.json": "cdd605fcc6df19840e203999b8fb5e3e9be66580189843eeb0b0f917d31dd736",
    "sources/curated-official-2026-07-20-joule-bettergrid-phase-1.json": "4426ff573e5c5c62bd44edd752bee3102b26d34edc5184ae5dd15a11a075e1da",
    "sources/curated-official-2026-07-20-menlo-digital-md-phx1-phoenix.json": "6aca705019ecc1629c14cd96320ac3a1a7fb33e12f8ffa937dc4d6984d3d3281",
    "sources/curated-official-2026-07-20-menlo-digital-md-va1-herndon.json": "8957e43eaad55b46b36ed8a72db30cb145614158c257400c4013a89b062b24e4",
    "sources/curated-official-2026-07-20-meta-richland-parish-5gw-compute-successor.json": "ea2ad4357ec401be3089b3ee6df9411d2ef466d6ea2daf971f0f39fa5ef9bf84",
    "sources/curated-official-2026-07-20-pdg-jh1-johor-phase-4.json": "48fcdcba2a0911553110dd4c22940ef4955cde1a5a3c7d4edddf6a451537c94b",
    "sources/curated-official-2026-07-20-pdg-jh1-johor-phase-5.json": "baacbb508a3cca52bd56f2b2f224bc080b154b644e05474c0115667538837a7c",
    "sources/curated-official-2026-07-20-racks-central-johor-ai-campus-rcjm1.json": "66cf889e5396a5c766af433cc142eb78edaded1fa868ad0e7c5093c0994b87b6",
    "sources/curated-official-2026-07-20-serverfarm-ctx2-houston-topout.json": "dfd38f20bd4d8b2bcbf927cae5b5915d9e769e9f687aa7255801730d08673941",
    "sources/curated-official-2026-07-20-stt-navi-mumbai-2.json": "c39ef82aa21969f405a6c3750348f517d26da9169881371e8bd29247a19c69d6",
    "sources/curated-official-2026-07-20-stt-navi-mumbai-3.json": "0387265e803a16bb3bb43ffc869cc53de07071b04c4c5cee128f32e001e8e7c1",
    "sources/curated-official-2026-07-20-stt-palava-first-data-centre.json": "0fbcc8f7bee88339e2665f56237ef6ecfc06db849cb9cbf42e936446054d2a3c",
    "sources/curated-official-2026-07-20-vantage-zrh12-winterthur-topout.json": "587318195fb538e94bbbea1aea27abe12f47e7526b055acd8d22143815d13515",
}

EXCLUDED_INPUTS = {
    "sources/curated-official-2026-07-20-hyperco-dayone-koria.json": "56aa92523a7b51b140bfaa161e278ce5380423945d32a2b1bf744c9b385afa63",
    "sources/curated-official-2026-07-20-teraco-jb7-isando.json": "d76b0a162d7894e0738a39feb4505a5460e28b86cc2f7daa4deb9f9e00cf7092",
    "sources/curated-official-2026-07-20-vnet-e-js03b.json": "acfae78267f91e6820b9f4d22a35fa3a828e4c9d53ae17b8ed58042a4f72330b",
    "sources/curated-official-2026-07-20-vnet-n-hb02.json": "6e0a83110457229986e6ab703954c221b5d6904b4a480c22dc9b65a1e05d79a6",
    "sources/curated-official-2026-07-20-vnet-n-hb03.json": "1bfdc6e845755e11871c882c4b80292f53f2407c6cdd25c30f69c504dfce5a01",
    "sources/curated-official-2026-07-20-vnet-n-hb04.json": "c89b4c2b0f93307e85f4fa5cb187c4157552c7d15eaea11587a59da4883fcfe9",
    "sources/curated-official-2026-07-20-vnet-n-or01.json": "b5963e09b58ec96fcd6065959ee9ee7b0c900ac15baa40dad99f813f543f7a4f",
    "sources/curated-official-2026-07-20-vnet-n-or02a.json": "0f7f78b11809e2d926df5820e6999b7dd843278fc6454a0249fb7dae7efda697",
    "sources/curated-official-2026-07-20-vnet-n-or02b.json": "50278632f21512a44c8d9549915f7a7239c6e21e9f5a49d04858802a07609645",
    "sources/curated-official-2026-07-20-vnet-n-or03.json": "4a6413620c698fda95ff58b90238b20b4ae474073bfe437b92f80bd5d21f31bb",
}
EXCLUDED_TEST_HASHES = {
    "tests/test_curated_vnet_q1_2026.py": "7b34e6d1229b3a3daf66c4ae2fff476b437a1e3a8642492b5cb04331cc1d0966",
}
EXCLUDED_MARKERS = tuple(
    marker.encode("ascii")
    for marker in (
        *EXCLUDED_INPUTS,
        *EXCLUDED_INPUTS.values(),
        *EXCLUDED_TEST_HASHES,
        *EXCLUDED_TEST_HASHES.values(),
        "curated:teraco-isando-campus",
        "teraco-jb7-construction-commencement-2024-11-13-captured-2026-07-20",
        "vnet_q1_2026",
    )
)

# common, added count/hash, removed count/hash
CSV_DELTA_CONTRACT = {
    "entities.csv": (
        542,
        31,
        "100852b5baedffb2f234acd9957b853d2ba07581446e5b4920c60f8b4c58ed21",
        2,
        "07524a6cd26aa7a1cf7ed252b6779c91bfbac3b873a572d7312e13e1702dc11c",
    ),
    "construction_pipeline.csv": (
        283,
        16,
        "34dc0ea988b16961e49d258cbf15b948ed066cb38908bc9980beccb6a34c7d4b",
        1,
        "f93b21365d7df7a755eb351b3295c5c165f9fe57600771ae7fe2e89516b3c5b6",
    ),
    "evidence.csv": (
        308,
        19,
        "53e50491dc1043c8d263ce4fcfc9377d0406b31d764e85a09c1d2ea8ae444d9a",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "capacity_estimates.csv": (
        441,
        8,
        "b31b4765c46a0673b72cdf15e5c1908df3709137f3c26d329653cf32fb336f21",
        0,
        "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570",
    ),
    "construction_source_signals.csv": (
        208,
        13,
        "8e06168f11ab50de6c041ed00842c35f4318b8480c8c88aa016d5459fc938127",
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

META_CAMPUS = "curated:meta-richland-parish-data-center"
META_PROJECT = META_CAMPUS + ":current-development"
META_OLD_EVIDENCE_ID = "624ec417-5585-529d-82ea-ffd8d3978dc4"
META_NEW_EVIDENCE_ID = "419fd6f7-5155-51eb-94f6-c77bb6f5c7e1"


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


class OpenSeedV44Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        offline = AssertionError("v44 validation attempted network access")
        excluded = {(ROOT / relative).resolve() for relative in EXCLUDED_INPUTS}
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text

        def guarded_read_bytes(path: Path) -> bytes:
            if path.resolve() in excluded:
                raise AssertionError(f"v44 attempted excluded input access: {path}")
            return original_read_bytes(path)

        def guarded_read_text(path: Path, *args: object, **kwargs: object) -> str:
            if path.resolve() in excluded:
                raise AssertionError(f"v44 attempted excluded input access: {path}")
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
        self.assertEqual(first["entities"], 573)
        self.assertEqual(first["entities_by_kind"], {"campus": 312, "project": 261})
        self.assertEqual(first["evidence_records"], 327)
        self.assertEqual(first["capacity_estimates"], 449)
        self.assertEqual(first["construction_pipeline_records"], 299)
        self.assertEqual(first["construction_source_signals"], 221)
        self.assertEqual(first["resolution_candidates"], 4)

        payloads = [DEFINITION.read_bytes(), *frozen.values()]
        for marker in EXCLUDED_MARKERS:
            self.assertFalse(any(marker in payload for payload in payloads), marker)

    def test_definition_is_exact_v43_plus_16_and_timestamps_are_bounded(self) -> None:
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
        self.assertEqual(len(base_pins), 253)
        self.assertEqual(len(current_pins), 269)
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
        self.assertTrue(set(EXCLUDED_INPUTS).isdisjoint(current_pins))

        retrieved_at: list[str] = [current["epoch_capture"]["retrieved_at"]]
        for relative, expected in current_pins.items():
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertFalse(path.is_symlink(), relative)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644, relative)
            self.assertEqual(sha256(path), expected, relative)
            document = json.loads(path.read_text(encoding="utf-8"))
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
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v44")
        self.assertEqual(current["publication_contract_version"], 4)
        self.assertEqual(current["epoch_capture"], base["epoch_capture"])
        self.assertEqual(current["expected_epoch_result"], base["expected_epoch_result"])
        self.assertEqual(current["scope"], base["scope"])

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

        evidence_keys = Counter()
        for relative in ADDED_INPUTS:
            document = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            evidence_keys.update(record["key"] for record in document["evidence"])
        self.assertEqual(sum(evidence_keys.values()), 31)
        self.assertEqual(len(evidence_keys), 29)
        self.assertEqual(
            {key: count for key, count in evidence_keys.items() if count > 1},
            {
                "pdg-jh1-johor-phases-4-5-milestones-2025-12-09-captured-2026-07-20": 2,
                "stt-navi-mumbai-2-3-construction-start-2024-11-07-captured-2026-07-20": 2,
            },
        )

    def test_exact_v43_to_v44_csv_delta_and_meta_replacement(self) -> None:
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

        self.assertEqual(
            (RELEASE / "resolution_candidates.json").read_bytes(),
            (BASE_RELEASE / "resolution_candidates.json").read_bytes(),
        )

        before_entities = by_key(BASE_RELEASE / "entities.csv", "stable_key")
        after_entities = by_key(RELEASE / "entities.csv", "stable_key")
        self.assertFalse(set(before_entities) - set(after_entities))
        self.assertEqual(len(set(after_entities) - set(before_entities)), 29)
        self.assertEqual(
            Counter(
                (
                    after_entities[key]["entity_kind"],
                    after_entities[key]["status"],
                )
                for key in set(after_entities) - set(before_entities)
            ),
            {
                ("campus", ""): 14,
                ("project", "shell"): 7,
                ("project", "site_preparation"): 1,
                ("project", "under_construction"): 7,
            },
        )
        changed = {
            key
            for key in set(before_entities) & set(after_entities)
            if before_entities[key] != after_entities[key]
        }
        self.assertEqual(changed, {META_CAMPUS, META_PROJECT})

        for key in (META_CAMPUS, META_PROJECT):
            old = before_entities[key]
            current = after_entities[key]
            self.assertEqual((old["latitude"], old["longitude"]), ("32.43", "-91.76"))
            self.assertEqual(old["operator"], "Meta")
            self.assertIn('"role:developer":"Meta"', old["tags_json"])
            self.assertEqual(current["latitude"], "")
            self.assertEqual(current["longitude"], "")
            self.assertEqual(current["operator"], "")
            self.assertEqual(current["geometry_json"], "null")
            self.assertNotIn("role:developer", current["tags_json"])
            self.assertNotIn("role:operator", current["tags_json"])
            self.assertEqual(current["snapshot_as_of"], "2026-07-13")
            self.assertEqual(current["snapshot_evidence_id"], META_NEW_EVIDENCE_ID)
            self.assertEqual(
                current["source_url"],
                "https://about.fb.com/news/2026/07/teachers-local-businesses-win-as-meta-expands-louisiana-data-center/",
            )

        self.assertEqual(after_entities[META_PROJECT]["status"], "under_construction")
        self.assertEqual(after_entities[META_PROJECT]["status_as_of"], "2026-04-28")
        self.assertEqual(
            after_entities[META_PROJECT]["status_evidence_id"],
            META_OLD_EVIDENCE_ID,
        )

        before_pipeline = by_key(
            BASE_RELEASE / "construction_pipeline.csv", "stable_key"
        )
        after_pipeline = by_key(RELEASE / "construction_pipeline.csv", "stable_key")
        self.assertFalse(set(before_pipeline) - set(after_pipeline))
        self.assertEqual(len(set(after_pipeline) - set(before_pipeline)), 15)
        self.assertEqual(
            {
                key
                for key in set(before_pipeline) & set(after_pipeline)
                if before_pipeline[key] != after_pipeline[key]
            },
            {META_PROJECT},
        )

    def test_added_capacity_and_nonaggregation_guardrails(self) -> None:
        before = row_counter(BASE_RELEASE / "capacity_estimates.csv")
        after = row_counter(RELEASE / "capacity_estimates.csv")
        entity_keys = {
            row["entity_id"]: row["stable_key"]
            for row in rows(RELEASE / "entities.csv")
        }
        added = [dict(packed) for packed in (after - before).elements()]
        observed = {
            (
                entity_keys[row["entity_id"]],
                row["metric"],
                row["stage"],
                row["base"],
                row["unit"],
                row["as_of_date"],
            )
            for row in added
        }
        self.assertEqual(
            observed,
            {
                ("curated:digital-halo-johor-campus:jhb1", "critical_it_mw", "planned", "20.0", "MW", "2026-04-27"),
                ("curated:menlo-digital-md-phx1-phoenix-campus", "critical_it_mw", "planned", "180.0", "MW", "2026-07-20"),
                ("curated:menlo-digital-md-phx1-phoenix-campus", "grid_connection_mw", "contracted", "257.0", "MW", "2026-07-20"),
                ("curated:menlo-digital-md-va1-herndon-data-center:48mw-facility-build", "critical_it_mw", "planned", "48.0", "MW", "2026-04-23"),
                ("curated:menlo-digital-md-va1-herndon-data-center:48mw-facility-build", "grid_connection_mw", "contracted", "67.2", "MW", "2026-07-20"),
                ("curated:stt-palava-data-centre-campus", "critical_it_mw", "planned", "400.0", "MW", "2026-03-17"),
                ("curated:stt-palava-data-centre-campus:first-data-centre", "critical_it_mw", "planned", "50.0", "MW", "2026-03-17"),
                ("curated:vantage-zrh1-winterthur-campus", "critical_it_mw", "planned", "40.0", "MW", "2026-07-20"),
            },
        )
        self.assertEqual(len(added), 8)
        self.assertFalse(
            any(key.startswith("curated:ascenty-sumare") for key, *_ in observed)
        )

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["capacity_estimates_current"], 449)
        self.assertNotIn("capacity_base_totals", summary)
        self.assertFalse(summary["capacity_aggregation"]["base_totals_published"])
        self.assertFalse(summary["capacity_aggregation"]["cross_entity_sum_valid"])
        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("does not publish aggregate capacity totals", readme)
        self.assertIn("not a global census", readme)
        self.assertIn("not a claim of parity with SemiAnalysis", readme)

    def test_builder_refuses_existing_or_symlink_output(self) -> None:
        script = ROOT / "scripts" / "build_open_seed.py"
        spec = importlib.util.spec_from_file_location("open_seed_v44_builder", script)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory(
            prefix="open-seed-v44-collision-", dir="/private/tmp"
        ) as temporary:
            temporary_path = Path(temporary)
            existing = temporary_path / "existing"
            existing.mkdir()
            dangling = temporary_path / "dangling"
            dangling.symlink_to(temporary_path / "missing")
            for output in (existing, dangling):
                with self.subTest(output=output), self.assertRaisesRegex(
                    SystemExit, "output directory already exists"
                ):
                    module.main(
                        [
                            "--epoch-input",
                            "unused.zip",
                            "--epoch-retrieved-at",
                            "2026-07-19T11:52:13Z",
                            "--curated-dir",
                            "unused-curated",
                            "--output-dir",
                            str(output),
                            "--as-of",
                            "2026-07-20",
                            "--recorded-at",
                            RECORDED_AT,
                            "--publication-contract-version",
                            "4",
                        ]
                    )


if __name__ == "__main__":
    unittest.main()
