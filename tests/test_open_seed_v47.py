from __future__ import annotations

from collections import Counter, defaultdict
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
DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v47.json"
RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v47"
BASE_DEFINITION = ROOT / "sources" / "open-seed-2026-07-20-v44.json"
BASE_RELEASE = ROOT / "releases" / "2026-07-20-open-seed-v44"

DEFINITION_SHA256 = "af6d130e0139495d0569115614d8112b56b7a16a5cc158efdcf24115fc076db2"
MANIFEST_SHA256 = "c0e228ed27e28830b466592bfc9a937f3c0d684be4fb97c7a20ac78e1c8a22a1"
BASE_DEFINITION_SHA256 = (
    "1f48d108b17e428ba48d6f5497b7590bca7d514830b6812d1e5f8913f195c312"
)
BASE_MANIFEST_SHA256 = (
    "908e1bc368d7c18d004303e5638a0814dc8ed2294a30175caec12b5e0837bdf9"
)
RECORDED_AT = "2026-07-20T09:50:12Z"
INSTRUCTION_FLOOR = "2026-07-20T09:50:12Z"
MAX_SELECTED_RETRIEVED_AT = "2026-07-20T09:25:15Z"
VNET_RETRIEVED_AT = "2026-07-20T07:24:19Z"
VNET_EVIDENCE_ID = "bb4018ca-2cb3-507e-b6a7-70c41d1ded23"

ADDED_INPUTS = {
    "sources/curated-official-2026-07-20-alto-sp01-granada.json": (
        "5e2f4e431b877d403d3f34d1d5de689450cfa58d1670c9e8b038f39f21d5cc80"
    ),
    "sources/curated-official-2026-07-20-digipower-columbiana-shell.json": (
        "7728f26d064c0ec3a47ac34aa60fdb635770a7b49e2fa90c4a0de91ca91e2ace"
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
    "sources/curated-official-2026-07-20-stack-stafford-first-topout.json": (
        "76a344cb2138728572ec12789df5b6bc9d4bfc509e32664ebc15e294b3003602"
    ),
    "sources/curated-official-2026-07-20-vnet-e-js03b-v2.json": (
        "fca0e08c8a0348e54596d9b3009d3b61a4602bfb44e143530827d338f69cf933"
    ),
    "sources/curated-official-2026-07-20-vnet-n-hb02-v2.json": (
        "d564746bc94cc05f93344ea427fce48796de9b6747bcf8b9073e2e1aef0d2522"
    ),
    "sources/curated-official-2026-07-20-vnet-n-hb03-v2.json": (
        "06fe2a9d44ce961c06e8ea168d5a444fb3aec5da248cbbc178abe693e0c8e7c7"
    ),
    "sources/curated-official-2026-07-20-vnet-n-hb04-v2.json": (
        "d109533127851b157df10ad017b552ea50ca82d6571386d7ae70a1efaf210854"
    ),
    "sources/curated-official-2026-07-20-vnet-n-or01-v2.json": (
        "698b8cf3ec1ed5b578589dc1b9c34d92e30ab19305e0f242825862473447eb8f"
    ),
    "sources/curated-official-2026-07-20-vnet-n-or02a-v2.json": (
        "6645c9853e1c4efe4c366e00086513f3ef7ca10b22c7cff512abca16053e8a82"
    ),
    "sources/curated-official-2026-07-20-vnet-n-or02b-v2.json": (
        "d84c2febccae8c6c7c871fcd2bca7a2e14462538fa2d5c26b590ba0c3258589b"
    ),
    "sources/curated-official-2026-07-20-vnet-n-or03-v2.json": (
        "980da0dea024ae56e6f30f855db78c9ce834c2ffc9dc5a024bfe9f8414ede895"
    ),
}

EXCLUDED_VNET_V1 = {
    "sources/curated-official-2026-07-20-vnet-e-js03b.json": "acfae78267f91e6820b9f4d22a35fa3a828e4c9d53ae17b8ed58042a4f72330b",
    "sources/curated-official-2026-07-20-vnet-n-hb02.json": "6e0a83110457229986e6ab703954c221b5d6904b4a480c22dc9b65a1e05d79a6",
    "sources/curated-official-2026-07-20-vnet-n-hb03.json": "1bfdc6e845755e11871c882c4b80292f53f2407c6cdd25c30f69c504dfce5a01",
    "sources/curated-official-2026-07-20-vnet-n-hb04.json": "c89b4c2b0f93307e85f4fa5cb187c4157552c7d15eaea11587a59da4883fcfe9",
    "sources/curated-official-2026-07-20-vnet-n-or01.json": "b5963e09b58ec96fcd6065959ee9ee7b0c900ac15baa40dad99f813f543f7a4f",
    "sources/curated-official-2026-07-20-vnet-n-or02a.json": "0f7f78b11809e2d926df5820e6999b7dd843278fc6454a0249fb7dae7efda697",
    "sources/curated-official-2026-07-20-vnet-n-or02b.json": "50278632f21512a44c8d9549915f7a7239c6e21e9f5a49d04858802a07609645",
    "sources/curated-official-2026-07-20-vnet-n-or03.json": "4a6413620c698fda95ff58b90238b20b4ae474073bfe437b92f80bd5d21f31bb",
}

EXCLUDED_GOODMAN = {
    "sources/curated-official-2026-07-20-goodman-ams01-amsterdam-v2.json": "802d18c2dab6091add67c798064c60dbed843a0c639abc3b843adaf68d77f1a0",
    "sources/curated-official-2026-07-20-goodman-ams01-amsterdam.json": "86b5bab9cd778409410e5cd769cc7d7878f1d96d5ac4a8fe12471ae7ca43abd4",
    "sources/curated-official-2026-07-20-goodman-fra02-frankfurt-v2.json": "2016970c6feda0ed1df7299c346713a29c86eed4088994f74fce515ddb809830",
    "sources/curated-official-2026-07-20-goodman-fra02-frankfurt.json": "f30db3b92de147265dfe281c307482f2679e57eecb7d436de8412179521408de",
    "sources/curated-official-2026-07-20-goodman-hkg09-kwai-chung-v2.json": "e4e0f0c9db3ce6295696427e425a41cc458441cc06d9413e8b6cab50a40367d1",
    "sources/curated-official-2026-07-20-goodman-hkg09-kwai-chung.json": "e61f745ba1b4af4d095b84de81d31c4960a20137786589a949002640c864627c",
    "sources/curated-official-2026-07-20-goodman-hkg10-tsuen-wan-v2.json": "ce187a48475f227603a73922320a14cf03b7f6c88374830e969f5cba6d1138b9",
    "sources/curated-official-2026-07-20-goodman-hkg10-tsuen-wan.json": "a6d006f832c90cc98b457dc4213e4c44d1ae01b80315ab14a492bbc69b568c92",
    "sources/curated-official-2026-07-20-goodman-lax01-los-angeles-v2.json": "296b17b45a9a6f56037b137ca68f37e549607317c2550b3e606a59e640528249",
    "sources/curated-official-2026-07-20-goodman-lax01-los-angeles.json": "5e79a2176b02b4be58d7531ef6a957e410ef28448e8dd7c8e9fc0f0d0839e9b7",
    "sources/curated-official-2026-07-20-goodman-par01-paris-v2.json": "f7d558d0e0234379ae3013bd794bd878a0c70ae9ccfcefd1718ee23406c6711c",
    "sources/curated-official-2026-07-20-goodman-par01-paris.json": "28179d0b0640362a2fa2405c8fb1564c408e3966fecac776267e091da1ea801a",
    "sources/curated-official-2026-07-20-goodman-par02-paris-v2.json": "f7e770519d244a8b57d7710c7ae1674ec2390bcd44f8d1b73d8c642adf5319c6",
    "sources/curated-official-2026-07-20-goodman-par02-paris.json": "2ea8e966b737170e2e74ae829c89e61c9eacdc89fc980ceef344454834791e81",
    "sources/curated-official-2026-07-20-goodman-syd01-macquarie-park-v2.json": "4667aea59067cd587bba475d9c42f26ac08e4edbdac058412b5a8df8a738d660",
    "sources/curated-official-2026-07-20-goodman-syd01-macquarie-park.json": "c09b538259662c918480f223912e622861cac5a25d0a6b946aa64d980e0e8561",
    "sources/curated-official-2026-07-20-goodman-ty005-tokyo-v2.json": "045cf3bb76bc9171ce017784562bcebab5eb5fc306c9ab017981631ce2e84764",
    "sources/curated-official-2026-07-20-goodman-ty005-tokyo.json": "7f73b491775f176a2ab1dbacad6842e1aca60b8797771d373bc6d48987f1b47d",
    "sources/curated-official-2026-07-20-goodman-ty006-tokyo-v2.json": "991f66bc60af577f47d2ad0a87ce861524ab805090d0215b1ff3bf5407dffdb4",
    "sources/curated-official-2026-07-20-goodman-ty006-tokyo.json": "76b5a70e873caa7993c18d2f546cfa993ea0ab1f110f22b5b4d7dde0c98715f0",
}

EXCLUDED_OTHER = {
    "sources/curated-official-2026-07-20-edged-atl01-3-atlanta-topout.json": "0213438b6b2844bbad14674ed8381e3a019c3d240ef55db3625c1543a4f98c06",
    "sources/curated-official-2026-07-20-edged-ord01-2-chicago-topout.json": "576e5d80846805d130dbebc50b0af8a23cbdac619ccf664dbf2421cdaeaa5a7c",
    "sources/curated-official-2026-07-20-hyperco-dayone-koria.json": "56aa92523a7b51b140bfaa161e278ce5380423945d32a2b1bf744c9b385afa63",
    "sources/curated-official-2026-07-20-teraco-jb7-isando.json": "d76b0a162d7894e0738a39feb4505a5460e28b86cc2f7daa4deb9f9e00cf7092",
}
EXCLUDED_INPUTS = EXCLUDED_VNET_V1 | EXCLUDED_GOODMAN | EXCLUDED_OTHER

INHERITED_EDGED_COUNCIL_BLUFFS = (
    "sources/curated-official-2026-07-20-edged-council-bluffs-first-data-center.json"
)
INHERITED_EDGED_COUNCIL_BLUFFS_SHA256 = (
    "d65f65e715c84fd6f93d6d248811c6a83258714a65244b6130e90c2ee77f5117"
)

REJECTED_MARKERS = {
    "sources/open-seed-2026-07-20-v45.json",
    "releases/2026-07-20-open-seed-v45",
    "tests/test_open_seed_v45.py",
    "2026-07-20-open-seed-v45",
    "c57e58d514fc69742b4dae5f8f1ea5244cc1f14aa1df6093d56abc8b779b6d13",
    "275f5767c5f08208be7178126855ce5d3a77b217dbd53b2483450c46673b7a27",
    "sources/open-seed-2026-07-20-v46.json",
    "releases/2026-07-20-open-seed-v46",
    "tests/test_open_seed_v46.py",
    "2026-07-20-open-seed-v46",
    "b6021710df7211611975dd946ef0a14c974b29a782161af821512a3a167a2293",
    "85ebc71e3751d722da2b24ae36abd62de8733ff331883d686ea74f5c3987418d",
    "curated:vnet-yangtze-river-delta-regional-wholesale-anchor",
    "curated:vnet-greater-beijing-area-regional-wholesale-anchor",
}
FORBIDDEN_PATH_FRAGMENTS = tuple(EXCLUDED_INPUTS) + (
    "sources/open-seed-2026-07-20-v45.json",
    "releases/2026-07-20-open-seed-v45",
    "sources/open-seed-2026-07-20-v46.json",
    "releases/2026-07-20-open-seed-v46",
)
FORBIDDEN_MARKERS = tuple(
    marker.encode("ascii")
    for marker in (*EXCLUDED_INPUTS, *EXCLUDED_INPUTS.values(), *REJECTED_MARKERS)
)

RELEASE_FILE_PINS = {
    "ATTRIBUTION.txt": (3107, "3072d55489f00b1c0621f291e11f8ee86542ace86970d63cfddfe2464274ea62"),
    "README.md": (2625, "ce2321c9a48775280250d5faa112548692503df1070992fb0db7a8446e321bf4"),
    "atlas.geojson": (2141735, "93e98acb8aab2dd98a90e722fe3311a132594ddb5b7128b0947c3f18bc941f64"),
    "capacity_estimates.csv": (211603, "e93a07c7e9930c822614dd2dd236a383f26cc7c3f9dd31673df5f13d351575a1"),
    "construction_pipeline.csv": (416455, "c833d71f2fc082ef1e6de0533aa7589caf6c89e9ad3415015d9b0f57d66d89ec"),
    "construction_source_signals.csv": (249819, "039a21836f9e9fbfd8acd8ef37fde3d5690d4632953966b32f3f39ef42d908a7"),
    "entities.csv": (672612, "7188cd19209dbbb6c25cd2cbb8f2502e5cb8e330b113e2273b3793388e31cf5b"),
    "evidence.csv": (129940, "fd4eefd7690b753b88c750dea51289068646b4112adab3d7df0e5c7a024d7a79"),
    "manifest.json": (8024, MANIFEST_SHA256),
    "resolution_candidates.csv": (4011, "4fe2af9c7ae416221e91e824d069e846a9346ae9be82987baff83ebab6beb897"),
    "resolution_candidates.json": (5874, "81f23af164d1d0eac5de421d7b217ad2481280dbeefebc7e01c2a1dbef96b1d0"),
    "source_inputs.json": (189158, "4f1954712525f9eb83dc3eaa52eb3da5e0610d1afadf20643343fdf149ad05c0"),
    "summary.json": (2804, "3dafc8d070458609445aba69e84dda73f5276973898068cb01a3344ffd47808f"),
}

# common, added count/hash, removed count/hash
CSV_DELTA_CONTRACT = {
    "entities.csv": (573, 28, "7ce5a828d1147e5dbe7bbf4a06d1b6161d0c024f2ce9e5c15d130e940aba8006", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "evidence.csv": (327, 10, "e16b907a50771b5b7a5f36d16881ef6a9abf475930bdc26a8deaccd7c5fc663c", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "capacity_estimates.csv": (449, 5, "135bfd8ddd31f21e2942a3c72eec4ae109ad12f092bf2add6099e6cef533c076", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "construction_pipeline.csv": (299, 14, "a8bdac0f6d6f0c2b8d28b182384011f385c46b21f6556433f1d5e17460559185", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "construction_source_signals.csv": (221, 7, "108f9fcbce64815a62f4cb4f6f3f548caac3c6c9b6a5b9c73eb62621e96e71b4", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
    "resolution_candidates.csv": (4, 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570", 0, "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"),
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
VNET_CAMPUS_KEYS = {
    f"curated:vnet-{slug}-locality-scoped-campus" for slug in VNET_SLUGS
}
VNET_PROJECT_KEYS = {
    f"curated:vnet-{slug}-locality-scoped-campus:{slug}-under-construction"
    for slug in VNET_SLUGS
}
OTHER_PROJECT_STATUS = {
    "curated:alto-sp01-granada-data-center-campus:phase-1-10mw-critical-it": "under_construction",
    "curated:digipowerx-columbiana-ai-data-center-campus:purpose-built-flagship-vertical-build": "shell",
    "curated:galaxy-helios-data-center-campus:phase-2-260mw-critical-it-build": "under_construction",
    "curated:hut8-beacon-point-ai-data-center-campus:first-phase-352mw-critical-it-lease": "announced",
    "curated:kasi-lekki-data-centre-campus:los1-first-building": "commissioning",
    "curated:stack-stafford-technology-campus:first-topped-out-data-center": "shell",
}
OTHER_CAMPUS_KEYS = {
    key.rsplit(":", 1)[0] for key in OTHER_PROJECT_STATUS
}
ADDED_ENTITY_KEYS = (
    VNET_CAMPUS_KEYS
    | VNET_PROJECT_KEYS
    | OTHER_CAMPUS_KEYS
    | set(OTHER_PROJECT_STATUS)
)
ADDED_EVIDENCE_IDS = {
    "21960c26-8fb4-5f89-b4cc-d4ee83d0be2d",
    "25d30d41-6ee8-521c-a8d5-5fc372370ebb",
    "2943a4a8-ef4a-5f43-9f4d-5be67ac22a5e",
    "4045942f-7692-538d-8e05-b1d0b97621e1",
    "685725e9-30ad-549a-ac10-7b2034a50b12",
    "8c104356-5de7-5156-9a00-2996e59f07af",
    "a17991df-ef8b-57e2-87fd-aea9770b9b44",
    "afb9a2fa-7d6d-57ef-8cbb-ef73595ed596",
    VNET_EVIDENCE_ID,
    "f9be097a-99d8-5f60-9672-146a49d37f53",
}
SIGNAL_EVIDENCE_IDS = {
    "21960c26-8fb4-5f89-b4cc-d4ee83d0be2d",
    "25d30d41-6ee8-521c-a8d5-5fc372370ebb",
    "2943a4a8-ef4a-5f43-9f4d-5be67ac22a5e",
    "685725e9-30ad-549a-ac10-7b2034a50b12",
    "8c104356-5de7-5156-9a00-2996e59f07af",
    VNET_EVIDENCE_ID,
    "f9be097a-99d8-5f60-9672-146a49d37f53",
}
EXPECTED_CAPACITIES = {
    ("curated:alto-sp01-granada-data-center-campus:phase-1-10mw-critical-it", "critical_it_mw", "planned", "10.0", "2026-07-09"),
    ("curated:galaxy-helios-data-center-campus:phase-2-260mw-critical-it-build", "critical_it_mw", "contracted", "260.0", "2026-07-06"),
    ("curated:hut8-beacon-point-ai-data-center-campus", "grid_connection_mw", "contracted", "1000.0", "2026-05-06"),
    ("curated:hut8-beacon-point-ai-data-center-campus:first-phase-352mw-critical-it-lease", "critical_it_mw", "contracted", "352.0", "2026-05-06"),
    ("curated:kasi-lekki-data-centre-campus", "critical_it_mw", "planned", "100.0", "2026-05-19"),
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


class OpenSeedV47Tests(unittest.TestCase):
    def _validate_offline(self) -> dict[str, object]:
        offline = AssertionError("v47 validation attempted network access")
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text

        def forbidden(path: Path) -> bool:
            rendered = path.resolve().as_posix()
            return any(marker in rendered for marker in FORBIDDEN_PATH_FRAGMENTS)

        def guarded_read_bytes(path: Path) -> bytes:
            if forbidden(path):
                raise AssertionError(f"v47 attempted forbidden input access: {path}")
            return original_read_bytes(path)

        def guarded_read_text(
            path: Path, *args: object, **kwargs: object
        ) -> str:
            if forbidden(path):
                raise AssertionError(f"v47 attempted forbidden input access: {path}")
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

        self.assertTrue(DEFINITION.is_file())
        self.assertFalse(DEFINITION.is_symlink())
        self.assertEqual(stat.S_IMODE(DEFINITION.stat().st_mode), 0o644)
        self.assertTrue(RELEASE.is_dir())
        self.assertFalse(RELEASE.is_symlink())
        self.assertEqual(stat.S_IMODE(RELEASE.stat().st_mode), 0o555)
        entries = list(RELEASE.iterdir())
        self.assertEqual({path.name for path in entries}, set(RELEASE_FILE_PINS))
        for path in entries:
            expected_bytes, expected_hash = RELEASE_FILE_PINS[path.name]
            self.assertTrue(path.is_file(), path.name)
            self.assertFalse(path.is_symlink(), path.name)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444, path.name)
            self.assertEqual(path.stat().st_size, expected_bytes, path.name)
            self.assertEqual(sha256(path), expected_hash, path.name)

        frozen = {path.name: path.read_bytes() for path in entries}
        first = self._validate_offline()
        second = self._validate_offline()
        self.assertEqual(first, second)
        self.assertEqual({path.name: path.read_bytes() for path in entries}, frozen)
        self.assertEqual(first["publication_contract_version"], 4)
        self.assertEqual(first["recorded_at"], RECORDED_AT)
        self.assertEqual(first["entities"], 601)
        self.assertEqual(first["entities_by_kind"], {"campus": 326, "project": 275})
        self.assertEqual(first["evidence_records"], 337)
        self.assertEqual(first["capacity_estimates"], 454)
        self.assertEqual(first["construction_pipeline_records"], 313)
        self.assertEqual(first["construction_source_signals"], 228)
        self.assertEqual(first["resolution_candidates"], 4)

        payloads = [DEFINITION.read_bytes(), *frozen.values()]
        for marker in FORBIDDEN_MARKERS:
            self.assertFalse(any(marker in payload for payload in payloads), marker)

    def test_definition_is_exact_v44_plus_fourteen_and_strictly_chronological(self) -> None:
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
        self.assertEqual(len(current_pins), 283)
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
        self.assertTrue(set(EXCLUDED_INPUTS).isdisjoint(current_pins))
        self.assertEqual(
            current_pins[INHERITED_EDGED_COUNCIL_BLUFFS],
            INHERITED_EDGED_COUNCIL_BLUFFS_SHA256,
        )

        retrieved_at = [current["epoch_capture"]["retrieved_at"]]
        for relative, expected in current_pins.items():
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertFalse(path.is_symlink(), relative)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644, relative)
            self.assertEqual(sha256(path), expected, relative)
            document = json.loads(path.read_text(encoding="utf-8"))
            timestamps = [row["retrieved_at"] for row in document.get("evidence", [])]
            if relative.startswith("sources/curated-official-2026-07-20-vnet-") and relative.endswith("-v2.json"):
                self.assertEqual(set(timestamps), {VNET_RETRIEVED_AT})
            retrieved_at.extend(timestamps)

        self.assertEqual(max(retrieved_at), MAX_SELECTED_RETRIEVED_AT)
        cutoff = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        floor = datetime.fromisoformat(INSTRUCTION_FLOOR.replace("Z", "+00:00"))
        maximum = datetime.fromisoformat(
            MAX_SELECTED_RETRIEVED_AT.replace("Z", "+00:00")
        )
        self.assertGreater(cutoff, maximum)
        self.assertGreaterEqual(cutoff, floor)
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
        self.assertEqual(current["release_id"], "2026-07-20-open-seed-v47")
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

    def test_exact_v44_to_v47_additive_release_delta(self) -> None:
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
        self.assertEqual(set(after_entities) - set(before_entities), ADDED_ENTITY_KEYS)
        self.assertFalse(set(before_entities) - set(after_entities))
        self.assertFalse(
            {
                key
                for key in set(before_entities) & set(after_entities)
                if before_entities[key] != after_entities[key]
            }
        )
        self.assertEqual(
            Counter(after_entities[key]["status"] for key in ADDED_ENTITY_KEYS),
            {"": 14, "under_construction": 10, "shell": 2, "announced": 1, "commissioning": 1},
        )

        before_pipeline = by_key(
            BASE_RELEASE / "construction_pipeline.csv", "stable_key"
        )
        after_pipeline = by_key(RELEASE / "construction_pipeline.csv", "stable_key")
        self.assertEqual(
            set(after_pipeline) - set(before_pipeline),
            VNET_PROJECT_KEYS | set(OTHER_PROJECT_STATUS),
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

    def test_selected_collisions_and_release_semantics_are_exact(self) -> None:
        base_definition = json.loads(BASE_DEFINITION.read_text(encoding="utf-8"))
        base_stable: set[str] = set()
        base_evidence: set[str] = set()
        for record in base_definition["curated_inputs"]:
            document = json.loads((ROOT / record["path"]).read_text(encoding="utf-8"))
            for kind in ("campus", "project"):
                entity = document.get(kind)
                if isinstance(entity, dict):
                    base_stable.add(entity["stable_key"])
            base_evidence.update(row["key"] for row in document.get("evidence", []))

        new_stable: defaultdict[str, list[str]] = defaultdict(list)
        new_evidence: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
        for relative in ADDED_INPUTS:
            document = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            for kind in ("campus", "project"):
                entity = document.get(kind)
                if isinstance(entity, dict):
                    new_stable[entity["stable_key"]].append(relative)
            for evidence in document.get("evidence", []):
                new_evidence[evidence["key"]].append(evidence)

        self.assertTrue(base_stable.isdisjoint(new_stable))
        self.assertTrue(base_evidence.isdisjoint(new_evidence))
        self.assertFalse({key: value for key, value in new_stable.items() if len(value) > 1})
        duplicated_evidence = {
            key: value for key, value in new_evidence.items() if len(value) > 1
        }
        self.assertEqual(
            {key: len(value) for key, value in duplicated_evidence.items()},
            {"vnet-1q26-ir-presentation-wholesale-construction-pdf-captured-2026-07-20": 8},
        )
        for records in duplicated_evidence.values():
            self.assertEqual(
                len(
                    {
                        json.dumps(row, sort_keys=True, separators=(",", ":"))
                        for row in records
                    }
                ),
                1,
            )

        before_entities = by_key(BASE_RELEASE / "entities.csv", "stable_key")
        entities = by_key(RELEASE / "entities.csv", "stable_key")
        added = {
            key: entities[key] for key in set(entities) - set(before_entities)
        }
        for key, row in added.items():
            self.assertEqual(row["latitude"], "", key)
            self.assertEqual(row["longitude"], "", key)
            self.assertEqual(row["geometry_json"], "null", key)

        for key in VNET_CAMPUS_KEYS | VNET_PROJECT_KEYS:
            row = entities[key]
            self.assertEqual(row["capacity_estimates_json"], "[]", key)
            self.assertEqual(row["workloads_json"], "[]", key)
            self.assertEqual(row["owner"], "", key)
            self.assertEqual(row["operator"], "", key)
            self.assertEqual(row["tenants"], "", key)
            self.assertEqual(row["snapshot_evidence_id"], VNET_EVIDENCE_ID, key)
            if key in VNET_PROJECT_KEYS:
                self.assertEqual(row["status"], "under_construction", key)
                self.assertEqual(row["operating_model"], "wholesale_colocation", key)
            else:
                self.assertEqual(row["status"], "", key)
                self.assertEqual(row["operating_model"], "", key)

        for key, expected_status in OTHER_PROJECT_STATUS.items():
            self.assertEqual(entities[key]["status"], expected_status, key)
        self.assertEqual(
            entities["curated:kasi-lekki-data-centre-campus:los1-first-building"]["capacity_estimates_json"],
            "[]",
        )
        self.assertEqual(
            entities["curated:hut8-beacon-point-ai-data-center-campus:first-phase-352mw-critical-it-lease"]["status_method"],
            "authoritative_announcement",
        )

        entity_keys = {
            row["entity_id"]: row["stable_key"]
            for row in rows(RELEASE / "entities.csv")
        }
        before_capacity = row_counter(BASE_RELEASE / "capacity_estimates.csv")
        after_capacity = row_counter(RELEASE / "capacity_estimates.csv")
        added_capacity = [dict(packed) for packed in (after_capacity - before_capacity).elements()]
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

        summary = json.loads((RELEASE / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["capacity_estimates_current"], 454)
        self.assertNotIn("capacity_base_totals", summary)
        self.assertFalse(summary["capacity_aggregation"]["base_totals_published"])
        self.assertFalse(summary["capacity_aggregation"]["cross_entity_sum_valid"])
        readme = (RELEASE / "README.md").read_text(encoding="utf-8")
        self.assertIn("does not publish aggregate capacity totals", readme)
        self.assertIn("not a global census", readme)
        self.assertIn("not a claim of parity with SemiAnalysis", readme)


if __name__ == "__main__":
    unittest.main()
