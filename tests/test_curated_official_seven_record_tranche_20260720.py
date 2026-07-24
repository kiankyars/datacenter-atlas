from __future__ import annotations

import copy
from contextlib import ExitStack
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
RECORDED_AT = "2026-07-21T02:12:00Z"
FIRST_ACCEPTED_SEED_VERSION = 59
FIRST_ACCEPTED_DEFINITION = (
    ROOT / "sources" / "open-seed-2026-07-20-v59.json"
)
FIRST_ACCEPTED_DEFINITION_SHA256 = (
    "3f48bd7bcc3087207fb0993bfc3050bc3c3a35930c125bce2c6aba635bc5e03f"
)
FIRST_ACCEPTED_MANIFEST = (
    ROOT / "releases" / "2026-07-20-open-seed-v59" / "manifest.json"
)
FIRST_ACCEPTED_MANIFEST_SHA256 = (
    "0f9214e65a851f81debd87a4e2c57ddd2146f793677707695ed2a01bcb8d88dd"
)
HISTORICAL_INCLUSION_SEED_VERSION = 67
STALE_EXCLUDED_SOURCE_NAME = (
    "curated-official-2026-07-20-stt-johor-1-current-build.json"
)
CAPTURE_DIRECTORY = Path("/private/tmp/official-seven-capture.Yv9Qgs")
ARTIFACT = (
    ROOT
    / "source_artifacts"
    / "official-source-seven-record-tranche-2026-07-20-v1"
)

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-20-stt-johor-1-current-build.json": {
        "bytes": 9468,
        "sha256": "785959fb2fb9962e1acefbd954ebb40b7d91305d180391c6311fc128c8899e7e",
        "evidence": 3,
        "lifecycle": 1,
        "capacities": 2,
        "latest": ("under_construction", "2025-02-24"),
    },
    "curated-official-2026-07-20-vantage-va4-fredericksburg-current-build.json": {
        "bytes": 9025,
        "sha256": "ddde1773cfa97ba3ed167ca1737c08bc5ac8d88657049852076b1a2d8ac0ea2b",
        "evidence": 3,
        "lifecycle": 1,
        "capacities": 1,
        "latest": ("under_construction", "2025-11-06"),
    },
    "curated-official-2026-07-20-stt-fairview-1-current-rollout.json": {
        "bytes": 9452,
        "sha256": "2a3d4a19385acd90f7b1f23480173bbddad52dbf348a9605e2ea40806202d249",
        "evidence": 3,
        "lifecycle": 1,
        "capacities": 2,
        "latest": ("expansion", "2026-03-31"),
    },
    "curated-official-2026-07-20-stt-cavite-2-phase-1-current-status.json": {
        "bytes": 8372,
        "sha256": "b223cd9b9ac5e179dc4edaf4f1b8eefd18737d2149f5c28a4937a65f5752f0c9",
        "evidence": 3,
        "lifecycle": 1,
        "capacities": 1,
        "latest": ("operational", "2026-03-31"),
    },
    "curated-official-2026-07-20-kio-mex8-mexico-city-current-build.json": {
        "bytes": 4343,
        "sha256": "390e80122c70d90592488ad2dce0d95c90c9d5d01197659d34b8ba782b2828d1",
        "evidence": 1,
        "lifecycle": 1,
        "capacities": 0,
        "latest": ("under_construction", "2026-03-09"),
    },
    (
        "curated-official-2026-07-20-google-saint-ghislain-"
        "seventh-building-expansion.json"
    ): {
        "bytes": 9486,
        "sha256": "23ae233655b96e7837919578318ff246af18bc9cfe96eaef4613983c0910623a",
        "evidence": 3,
        "lifecycle": 2,
        "capacities": 0,
        "latest": ("expansion", "2026-05-06"),
    },
    "curated-official-2026-07-20-scala-smextp01-tepotzotlan-current-status.json": {
        "bytes": 9193,
        "sha256": "0c528badf9cdd2dd0a7d4a8cfef1fc883f5cbec85025c36a2ca2d46c5596ca86",
        "evidence": 3,
        "lifecycle": 1,
        "capacities": 1,
        "latest": ("operational", "2026-07-20"),
    },
}

ARTIFACT_FILE_SPECS = {
    "README.md": (
        3097,
        "46766b571d0a81774dc57db461f2223ff0a48d7e6eb46a9078ac86f9b73947ca",
    ),
    "manifest.json": (
        704,
        "ce40b62bc69430eb5e3b5452bc9e462457fe968f33fe68983e69c2275acca74c",
    ),
    "manifest.sha256": (
        80,
        "ba8031be70dc13f376d40ce5b813daaeb74abeb0dab69cc9cbd35abc85be3441",
    ),
    "retrieval-inventory.json": (
        29389,
        "d4dffd0463617c40486c4aae1feb42dd1735f01976d7951376a886830704127d",
    ),
    "source-snapshot.json": (
        6721,
        "28dd41511e0a532ec4efe6fb326dfa02ebb451df35b4c72c8c19b706564b4366",
    ),
}

# body, headers, curl writeout, HTTP status, curl exit, inventory use
CAPTURE_SPECS: dict[str, tuple[Any, ...]] = {
    "globe_17q": (
        (6105, "f07d6d8cf6c6fb0fd9aac15b0892f1346a7ca2f92f36df7880157dc5ddd49aaf"),
        (2463, "08e7c397546afa0bc120450b286b638135e0295f1e89073d4090eb31e2aa2a24"),
        (9940, "e41ef0d4100602f81acd9cb4c5d23b9dd725e0c90e5841d7302b24c5d4d51a2c"),
        403,
        22,
        "blocked_candidate_http_403",
    ),
    "globe_ir": (
        (5783, "27c37359973aa11b6cb8096511e0250d0703f2f260c90f409585753d361f4da4"),
        (2466, "492b9deffce5cc749a8bc0261abf622a95c9268d29d362eb63f88ad08c0e5abd"),
        (9651, "9b2afd8802ee212ccb0a73dccc976cde5527701c2ba0266a909683bed272dfd8"),
        403,
        22,
        "blocked_candidate_http_403",
    ),
    "globe_mpower": (
        (5864, "3bf13c4d2f941282d01799fb55837cebd5b69e57733570e4d520639ad79dd811"),
        (2462, "324da8830daf72d5de543c48e6e9f8210fb0d69a928584f6fe2e66d06c4419b7"),
        (9735, "13c2f898867bd4ba3a016e6010c40577c262401d55952082d38ad6543ced2f14"),
        403,
        22,
        "blocked_candidate_http_403",
    ),
    "globe_q1": (
        (6175, "fe861aa7439e4821fda5cc4927b1a5893e010bde049c8bb6ee2c2d660cc9a40e"),
        (2470, "dd81bd59cf6a8ee0fd7c0fb0ad1f25b508f4bb779f4e2f238bc2d6e387b8283a"),
        (10003, "a295cc66c21049cb4d4f9beec9bdbce37dd88028ef1268435dd63ee1ba03e42e"),
        403,
        22,
        "blocked_candidate_http_403",
    ),
    "globe_q1_browser_ua": (
        (6303, "e379e62274a972fb9ebf3706c9fd31788b0c57d54e6c0426ae3ca6b54d51bffa"),
        (2472, "a34cb159a77cc966af0da8d997b92f71bf99a484fbe497e994b1ab26fac0df0c"),
        (10014, "c9a1147e849842289fcce868e355b9feeeefbb895c5f459596cdc116d06c974f"),
        403,
        22,
        "blocked_candidate_http_403",
    ),
    "google_blog": (
        (377998, "a1b15c5cd367468ca097bc6e9cfd433ccc09496dd40b8185a11e71c1d8dc0432"),
        (2799, "e825bba41eb5c07f6f75f0a66d75c5e21ed7f0e97e3903b765c851241e298360"),
        (15907, "1c9bc3bb2d09aae581e6c347b238e1b877ab976a7ba51447bcadf7751d268ea3"),
        200,
        0,
        "evidence",
    ),
    "google_linkedin": (
        (165813, "5fae1e72130a8d226c7446e0049e3846467235482f0173b55422b7b3ead4dc81"),
        (5378, "b9086064d19b0e59ae77d9755c29d947963852c8803fac63684b3c90bad8bad6"),
        (17736, "3456ffbd4351b69d8df564b801a25f9bc12d5733aedd36459ba2a1612a0746f0"),
        200,
        0,
        "evidence",
    ),
    "johor_page": (
        (58134, "753f25f99ab98b3a8894a95683b6b70067336306324ba224c456ee3d7cb87e0a"),
        (2986, "c693c07b490258434ad604c481e611037f169daae84a4bb8fcdc0ba471469782"),
        (14418, "f5392bfe15f077db91fbc2a71efe5ff710a73848ff435c0cba6edabed33c827b"),
        200,
        0,
        "evidence",
    ),
    "johor_pdf": (
        (742145, "6d7b0a7eea97f4de1c7e454f7538be0d83529d45e8949adb3049743b8b4872a5"),
        (735, "5933f4e7dd5b41ea1871da54cf26a1f2f3dd96bc3c45fda63663c17224fc653b"),
        (14707, "48f54ffd80700c6e6ca6c6f9fed04e3c53701f99ba740d95cc9b3cd0793b1306"),
        200,
        0,
        "evidence",
    ),
    "johor_release": (
        (75109, "732bf280c6d94daaa3afd0b9cb7875bc40737296109f39786a5cd8620b055ceb"),
        (2986, "33917ebd687097b320496bd9b87425f90638bd74d05618cdd98bd202f8d91513"),
        (14741, "d71b4d2213a0e071a2c46dbf23fbde9b1beebb6709e9d29f1ac2fc5eb33cbfc5"),
        200,
        0,
        "evidence",
    ),
    "kio_linkedin": (
        (161114, "a62e75817b9e8c85ccfe220f07d689852f1c848ab26ab394ddbaa24bfd1d5291"),
        (5239, "3c1b9ec0f99f60e6b49d8c33bf0168ee56a86fc97d65a533df753f807705fab0"),
        (18908, "2da924036c105886f1aa9cb02266bb830e041794825ee029d3157d92444ec9b2"),
        200,
        0,
        "evidence",
    ),
    "kio_locations": (
        (175274, "22d3c3e0f5dc9127934cb45d86d62a835142e59e3ca53af6d9f6dbba7ff0e037"),
        (680, "78542a8efbda54ef364683682ff7fda0418239d67aacd3d22af3253cf6629941"),
        (16194, "b1df39a7f5653c242e16bbcc6b9248e3d2ca9d3dad0bf80de2ea3ff262b40954"),
        200,
        0,
        "successful_exclusion_no_mex8",
    ),
    "kio_release": (
        (91768, "9f81ecbc325c1a2ff96767ac3c51061d90688a40b3355965c9f88769d1646bc7"),
        (1119, "8a7333c9f728559e589f7d5a1d35f66a532a01c84a0b31a69f3aadc022fbb036"),
        (16423, "2f895a78d2c0a4c93aea86f6248fd46dcb4010caf68eea9d92ceb6b173b4ee2a"),
        200,
        0,
        "successful_exclusion_generic_redirect",
    ),
    "pse_globe_17q": (
        (1460276, "66da77b690b61e6606785ef604b20582d7d9f8de51b939cfd7fed2002656c5af"),
        (432, "1ad5accbe5fb670e199b042d5265b04c2a0e1c4de628cee986e39bdfbbc301e9"),
        (14821, "064d90e97200e74d9061eb2bc6acb40d7511766a53e7adc48f83d409f715cd04"),
        200,
        0,
        "evidence",
    ),
    "pse_globe_viewer": (
        (4778, "e9168b8fc558894ec367e035d44eb01e3ef27d511f344bfe845017ecab514c51"),
        (453, "1e1f19fa799b2e76417e0c6f8ac1a0896b169c5a9f6bc5bdfe42815d118f3ea3"),
        (14912, "098c7f2e4e68cf6c986e5af5f70c079f654aed38d9f3ebda1ea51f6c4985759d"),
        200,
        0,
        "evidence",
    ),
    "pse_viewer": (
        (4846, "7f76f0a934003b69956516650e282d19797bcd96ba0ac613904772f1899c33eb"),
        (453, "8844fec34d47387c3d29993331c0615929b7f8c6427ce0749bf11740051ceec5"),
        (14906, "8d366f7fc5d22a355ee7a5be4aaeeaf2591d2ba4525fb92bf9664849c17f6198"),
        200,
        0,
        "successful_exclusion_wrong_globe_filing",
    ),
    "scala_cert": (
        (117202, "fbb3280e4a24ef91b1f846f22a8e32ce943cef4fbfe33ce1e760f341bd7ee974"),
        (343, "2e347e4a4ee1a13da7361ad1e30accdc23161757ef478cff39197e21b5d3e054"),
        (12255, "d4ffed9d4e42b46553f863e61db432531c582595851fd0a546bdc056f551bc6d"),
        200,
        0,
        "evidence",
    ),
    "scala_page": (
        (610118, "d99343592a53ce1b6cd7c3c8f8fa783ce7d856db53fd726f3726398fa237e043"),
        (519, "f93486660a5ea621986b1bb7e6e0b6ea56762037358e76dbf86f5918820a165c"),
        (11975, "0a646f40b7636305958f5a5233c3b06a415e53a0e946e275cd762d54ddfed5f2"),
        200,
        0,
        "evidence",
    ),
    "scala_release": (
        (303037, "61f00107074bb5066f8c751dbb30e8b06fca6ab3100b2560511ff4fa21102429"),
        (752, "dcbd94872517b65a88552637997be369ac6392d2a8949d6a916a6b42c4eec076"),
        (12309, "8b307fc265a9d027ef92965efaeeba656774f6598f584ed90ff0fc953f9c126f"),
        200,
        0,
        "evidence",
    ),
    "stt_calabarzon": (
        (70549, "864c1969d6d45e09ca55765bd5c4f4987509fd0a656d1314a7fcc6aab4d4100a"),
        (2982, "227b4a229cfb05617aa55ade59c552079439dcab5049fded36ede663e87abc70"),
        (14378, "82e100e667cdb2c4a79ad9083a72104e8f33a71accf3b18f38e01366ac3f50e0"),
        200,
        0,
        "evidence",
    ),
    "stt_manila": (
        (89733, "e6194c3a98aed9d5a35a2857a7a646822ef97ba2e5fc6e5f15f57fa82ce9e0f6"),
        (2982, "e97dd582d6a7f2266ba33da43b542120e1e077106bf4be4207d08024cb126aff"),
        (14358, "90406e1db5e0d410705b41bbd960f332bbc551ca07afcff702ff3dc8660dd073"),
        200,
        0,
        "evidence",
    ),
    "va4_page": (
        (220546, "1e1725d38bd57be8a621a0d5a37de0ee077ca93b3010c09e01e22e2df419aaba"),
        (2014, "b977b23f1ffe383789378c17a2af417b4bf3659528ed0a927812a0b7fda246e9"),
        (9545, "6c3f2dc1e7ac2506ae3f832e16cae39fe2f72e46767382223d4d912718442ee8"),
        200,
        0,
        "evidence",
    ),
    "va4_pdf": (
        (239997, "c2fec8b74abd65e94441093794c82da7a7aab45e58c80e6a150a11a6009d2eae"),
        (744, "5ac7b813cb42e5fc11bec59cbafdf4f98e5248b4fae9ce3cf7df2691cf63a926"),
        (9528, "9838955b9654266a25429fadb3e68d81b625ad54597c67fd7ac77418a7929bd3"),
        200,
        0,
        "evidence",
    ),
    "va4_release": (
        (192397, "c90d561cca9b90e80bc9334bbbb318832bd0de55d9c565bc67b2e0d6489244b2"),
        (2005, "df12c504b469d96b0ea6cc095936223a00f4696995e6ba8c878f8bbfad9d3837"),
        (9798, "78946879280a2529f0ea2bc26a8d6d3e26b07ce0bed211a4810a344292854b39"),
        200,
        0,
        "evidence",
    ),
    "wallonia": (
        (52044, "fffef4751c3e645a33afcaf41c15599b18b5bc636ba75a4c6457ae6f62da95ab"),
        (672, "51b8fd8e8e689220dd41e319fa65c06e9fd7b2b21183a9453ca9459d64a48d74"),
        (16525, "dc3211b5247f575fee72e38a2f3676fb7771bd36ce07f1d0cf8ecd7fc6d04bf1"),
        200,
        0,
        "evidence",
    ),
}

EXPECTED_CAPACITIES = {
    "curated:scala-smextp01-tepotzotlan-data-center:smextp01": (
        "design",
        5.1,
        "reported",
        "2026-07-20",
    ),
    "curated:stt-cavite-data-centre-campus:stt-cavite-2": (
        "planned",
        6.0,
        "reported",
        "2026-07-20",
    ),
    "curated:stt-fairview-data-centre-campus": (
        "planned",
        124.0,
        "calculated",
        "2026-07-20",
    ),
    "curated:stt-fairview-data-centre-campus:stt-fairview-1": (
        "planned",
        28.0,
        "reported",
        "2026-07-20",
    ),
    "curated:stt-johor-data-centre-campus": (
        "planned",
        120.0,
        "reported",
        "2025-12-01",
    ),
    "curated:stt-johor-data-centre-campus:stt-johor-1": (
        "planned",
        16.0,
        "reported",
        "2025-12-01",
    ),
    "curated:vantage-va4-fredericksburg-campus": (
        "planned",
        192.0,
        "reported",
        "2026-07-20",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OfficialSevenRecordTrancheTests(unittest.TestCase):
    def _source_paths(self) -> list[Path]:
        return [ROOT / "sources" / name for name in SOURCE_SPECS]

    def _documents(self) -> dict[str, dict[str, Any]]:
        return {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in self._source_paths()
        }

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("seven-record curated import attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=error))
        return stack

    def _write_document(self, path: Path, document: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _database_state(
        self, paths: list[Path], *, repetitions: int = 1
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for iteration in range(repetitions):
                        for path in paths:
                            result = CuratedOfficialSourceAdapterV11().import_file(
                                connection,
                                path,
                                recorded_at=RECORDED_AT,
                            )
                            self.assertEqual(result.warnings, ())
                            spec = SOURCE_SPECS[path.name]
                            self.assertEqual(
                                result.entities_created, 2 if iteration == 0 else 0
                            )
                            self.assertEqual(
                                result.evidence_created,
                                spec["evidence"] if iteration == 0 else 0,
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key FROM entities ORDER BY 1, 2",
                    "SELECT id, source_url, content_hash, retrieved_at "
                    "FROM evidence ORDER BY 1",
                    "SELECT entities.stable_key, status, as_of_date, method "
                    "FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id "
                    "ORDER BY 1, 3",
                    "SELECT entities.stable_key, as_of_date, method, latitude, "
                    "longitude FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id ORDER BY 1",
                    "SELECT entities.stable_key, metric, stage, base, method, "
                    "as_of_date FROM capacity_estimates JOIN entities "
                    "ON entities.id = capacity_estimates.entity_id ORDER BY 1",
                    "SELECT entity_id, operating_model "
                    "FROM operating_model_observations ORDER BY 1",
                    "SELECT entity_id, workload FROM workload_observations ORDER BY 1",
                )
                return tuple(
                    tuple(tuple(row) for row in connection.execute(query))
                    for query in queries
                )
            finally:
                connection.close()

    def _validate_artifact(self, artifact: Path, *, check_modes: bool = True) -> None:
        self.assertEqual(
            {path.name for path in artifact.iterdir() if path.is_file()},
            set(ARTIFACT_FILE_SPECS),
        )
        for name, (expected_bytes, expected_hash) in ARTIFACT_FILE_SPECS.items():
            path = artifact / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(len(path.read_bytes()), expected_bytes)
            self.assertEqual(sha256(path), expected_hash)
            if check_modes:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)

        manifest = json.loads((artifact / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            (artifact / "manifest.sha256").read_text(encoding="utf-8"),
            f"{ARTIFACT_FILE_SPECS['manifest.json'][1]}  manifest.json\n",
        )
        self.assertEqual(
            {entry["path"] for entry in manifest["files"]},
            {"README.md", "retrieval-inventory.json", "source-snapshot.json"},
        )
        for entry in manifest["files"]:
            path = artifact / entry["path"]
            self.assertEqual(len(path.read_bytes()), entry["bytes"])
            self.assertEqual(sha256(path), entry["sha256"])
        tree_payload = json.dumps(manifest["files"], indent=2, sort_keys=True) + "\n"
        self.assertEqual(
            hashlib.sha256(tree_payload.encode()).hexdigest(),
            manifest["tree_sha256"],
        )

    def _assert_exact_semantics(
        self, documents: dict[str, dict[str, Any]]
    ) -> None:
        self.assertEqual(set(documents), set(SOURCE_SPECS))
        observed_capacities: dict[str, tuple[Any, ...]] = {}
        for name, document in documents.items():
            spec = SOURCE_SPECS[name]
            self.assertEqual(document["schema_version"], "1.1")
            self.assertEqual(len(document["evidence"]), spec["evidence"])
            self.assertEqual(len(document["lifecycle"]), spec["lifecycle"])
            self.assertEqual(len(document["capacities"]), spec["capacities"])
            self.assertEqual(document["operating_models"], [])
            self.assertEqual(document["workloads"], [])
            latest = max(document["lifecycle"], key=lambda item: item["as_of_date"])
            self.assertEqual((latest["value"], latest["as_of_date"]), spec["latest"])
            for capacity in document["capacities"]:
                entity = document[capacity["entity"]]["stable_key"]
                observed_capacities[entity] = (
                    capacity["stage"],
                    float(capacity["base"]),
                    capacity["method"],
                    capacity["as_of_date"],
                )
        self.assertEqual(observed_capacities, EXPECTED_CAPACITIES)

    def test_sources_are_canonical_mode_and_byte_pinned(self) -> None:
        for path in self._source_paths():
            with self.subTest(source=path.name):
                spec = SOURCE_SPECS[path.name]
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertTrue(stat.S_ISREG(path.stat().st_mode))
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
                data = path.read_bytes()
                self.assertEqual(len(data), spec["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), spec["sha256"])
                text = data.decode("utf-8")
                document = json.loads(text)
                self.assertEqual(
                    text,
                    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                )
        self._assert_exact_semantics(self._documents())

    def test_capture_inventory_is_exact_closed_and_credential_free(self) -> None:
        inventory = json.loads(
            (ARTIFACT / "retrieval-inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(inventory["direct_request_attempts"], 25)
        self.assertEqual(inventory["completed_response_requests"], 25)
        self.assertEqual(inventory["successful_http_requests"], 20)
        self.assertEqual(inventory["failed_http_requests"], 5)
        self.assertEqual(inventory["evidence_supporting_requests"], 17)
        self.assertEqual(inventory["successful_exclusion_requests"], 3)
        self.assertFalse(inventory["request_credentials_supplied"])
        self.assertFalse(inventory["browser_session_used"])
        self.assertTrue(inventory["analysis_temporary_response_files_deleted"])
        self.assertFalse(inventory["raw_response_bodies_retained"])
        self.assertFalse(inventory["raw_response_headers_retained"])
        self.assertFalse(inventory["curl_writeouts_retained"])

        requests = {
            item["request_id"]: item
            for item in inventory["controlled_http_requests"]
        }
        self.assertEqual(set(requests), set(CAPTURE_SPECS))
        for request_id, expected in CAPTURE_SPECS.items():
            with self.subTest(request=request_id):
                item = requests[request_id]
                body, headers, writeout, status, exit_code, use = expected
                self.assertEqual(item["body"]["bytes"], body[0])
                self.assertEqual(item["body"]["sha256"], body[1])
                self.assertEqual(item["headers"]["bytes"], headers[0])
                self.assertEqual(item["headers"]["sha256"], headers[1])
                self.assertEqual(item["curl_writeout"]["bytes"], writeout[0])
                self.assertEqual(item["curl_writeout"]["sha256"], writeout[1])
                self.assertEqual(item["http_status"], status)
                self.assertEqual(item["curl_exit_code"], exit_code)
                self.assertEqual(item["use"], use)
                self.assertEqual(item["http_version"], "HTTP/2")
                self.assertEqual(item["curl_header_bytes"], headers[0])
                self.assertTrue(item["requested_url"].startswith("https://"))
                self.assertTrue(item["effective_url"].startswith("https://"))
                self.assertFalse(item["body"]["retained"])
                self.assertFalse(item["headers"]["retained"])
                self.assertFalse(item["curl_writeout"]["retained"])

        blocked = [item for item in requests.values() if item["http_status"] == 403]
        self.assertEqual(len(blocked), 5)
        self.assertTrue(
            all(urlparse(item["requested_url"]).hostname == "www.globe.com.ph" for item in blocked)
        )
        self.assertEqual(
            requests["globe_q1_browser_ua"]["user_agent_profile"],
            "desktop_browser_string_without_session",
        )
        self.assertEqual(requests["kio_release"]["redirect_count"], 1)
        self.assertEqual(requests["kio_release"]["response_header_blocks"], 2)
        self.assertEqual(
            requests["kio_release"]["effective_url"],
            "https://kiodatacenters.com/en/newsroom",
        )

        for document in self._documents().values():
            for evidence in document["evidence"]:
                metadata = evidence["metadata"]
                request = requests[metadata["capture_request_id"]]
                self.assertEqual(request["use"], "evidence")
                self.assertEqual(evidence["content_hash"], request["body"]["sha256"])
                self.assertEqual(
                    metadata["capture_headers_bytes"], request["headers"]["bytes"]
                )
                self.assertEqual(
                    metadata["capture_headers_sha256"], request["headers"]["sha256"]
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_bytes"],
                    request["curl_writeout"]["bytes"],
                )
                self.assertEqual(
                    metadata["capture_curl_writeout_sha256"],
                    request["curl_writeout"]["sha256"],
                )

    def test_import_is_offline_idempotent_and_order_independent(self) -> None:
        paths = self._source_paths()
        once = self._database_state(paths)
        self.assertEqual(self._database_state(paths, repetitions=2), once)
        self.assertEqual(self._database_state(list(reversed(paths))), once)
        entities, evidence, lifecycle, snapshots, capacities, models, workloads = once
        self.assertEqual(len(entities), 14)
        self.assertEqual(len(evidence), 19)
        self.assertEqual(len(lifecycle), 8)
        self.assertEqual(len(snapshots), 14)
        self.assertEqual(len(capacities), 7)
        self.assertEqual(models, ())
        self.assertEqual(workloads, ())
        self.assertEqual(
            {
                row[0]: (row[2], float(row[3]), row[4], row[5])
                for row in capacities
            },
            EXPECTED_CAPACITIES,
        )

    def test_freshness_status_and_capacity_exclusions_are_exact(self) -> None:
        documents = self._documents()
        self._assert_exact_semantics(documents)
        recorded_at = datetime.fromisoformat(RECORDED_AT.replace("Z", "+00:00"))
        for document in documents.values():
            for evidence in document["evidence"]:
                retrieved_at = datetime.fromisoformat(
                    evidence["retrieved_at"].replace("Z", "+00:00")
                )
                self.assertLessEqual(retrieved_at, recorded_at)

        by_fragment = {
            name.split("2026-07-20-", 1)[1].removesuffix(".json"): document
            for name, document in documents.items()
        }
        self.assertEqual(
            by_fragment["scala-smextp01-tepotzotlan-current-status"]["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "operational",
                    "evidence_key": (
                        "scala-current-portfolio-smextp01-in-operation-"
                        "captured-2026-07-20"
                    ),
                    "as_of_date": "2026-07-20",
                    "method": "authoritative_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        fairview = by_fragment["stt-fairview-1-current-rollout"]
        self.assertEqual(fairview["lifecycle"][0]["value"], "expansion")
        cavite = by_fragment["stt-cavite-2-phase-1-current-status"]
        self.assertEqual(cavite["lifecycle"][0]["value"], "operational")
        self.assertEqual(cavite["capacities"][0]["stage"], "planned")
        google = by_fragment["google-saint-ghislain-seventh-building-expansion"]
        self.assertEqual(
            [(item["value"], item["as_of_date"]) for item in google["lifecycle"]],
            [("under_construction", "2025-10-08"), ("expansion", "2026-05-06")],
        )
        self.assertEqual(google["capacities"], [])
        self.assertEqual(
            by_fragment["kio-mex8-mexico-city-current-build"]["capacities"], []
        )

        all_capacities = [
            capacity
            for document in documents.values()
            for capacity in document["capacities"]
        ]
        self.assertTrue(
            all(capacity["metric"] == "critical_it_mw" for capacity in all_capacities)
        )
        self.assertTrue(
            {4.0, 5.0, 7.9, 30.0, 40.5, 110.0, 270.0}.isdisjoint(
                {float(capacity["base"]) for capacity in all_capacities}
            )
        )
        snapshot = json.loads(
            (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        )
        boundary = snapshot["semantic_boundary"]
        for key in (
            "kio_untyped_4_mw_normalized",
            "vantage_270_mw_substation_normalized",
            "globe_platform_30_mw_forecast_normalized",
            "globe_40_5_mw_energy_partnership_normalized",
            "google_110_mw_energy_deals_normalized",
            "scala_superseded_5_and_7_9_mw_values_normalized",
            "forward_completion_or_rfs_forecasts_used_as_lifecycle",
            "linkedin_credentials_or_browser_session_used",
            "globe_cdn_403_responses_used_as_evidence",
        ):
            self.assertFalse(boundary[key])
        self.assertFalse(boundary["nested_capacity_pairs_are_additive"])

    def test_collision_resolution_guardrails_and_seed_lineage(self) -> None:
        documents = self._documents()
        source_names = set(documents)
        stable_keys = {
            document[entity]["stable_key"]
            for document in documents.values()
            for entity in ("campus", "project")
        }
        evidence_keys = {
            evidence["key"]
            for document in documents.values()
            for evidence in document["evidence"]
        }
        self.assertEqual(len(stable_keys), 14)
        self.assertEqual(len(evidence_keys), 19)

        collisions: dict[str, dict[str, list[str]]] = {}
        for path in sorted((ROOT / "sources").glob("*.json")):
            if path.name in source_names:
                continue
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            existing_stable = {
                entity["stable_key"]
                for entity in (existing.get("campus"), existing.get("project"))
                if isinstance(entity, dict) and isinstance(entity.get("stable_key"), str)
            }
            existing_evidence = {
                item["key"]
                for item in existing.get("evidence", [])
                if isinstance(item, dict) and isinstance(item.get("key"), str)
            }
            stable_overlap = sorted(stable_keys & existing_stable)
            evidence_overlap = sorted(evidence_keys & existing_evidence)
            if stable_overlap or evidence_overlap:
                collisions[path.name] = {
                    "stable": stable_overlap,
                    "evidence": evidence_overlap,
                }
        self.assertEqual(collisions, {})

        self.assertEqual(
            hashlib.sha256(FIRST_ACCEPTED_DEFINITION.read_bytes()).hexdigest(),
            FIRST_ACCEPTED_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(FIRST_ACCEPTED_MANIFEST.read_bytes()).hexdigest(),
            FIRST_ACCEPTED_MANIFEST_SHA256,
        )
        initially_accepted_source_names = source_names - {
            STALE_EXCLUDED_SOURCE_NAME
        }
        initially_expected_inputs = {
            name: spec["sha256"]
            for name, spec in SOURCE_SPECS.items()
            if name in initially_accepted_source_names
        }
        historically_inclusive_inputs = {
            name: spec["sha256"] for name, spec in SOURCE_SPECS.items()
        }
        for path in sorted((ROOT / "sources").glob("open-seed-*.json")):
            version_text = path.stem.rpartition("-v")[2]
            self.assertTrue(version_text.isdecimal(), path.name)
            version = int(version_text)
            definition = json.loads(path.read_text(encoding="utf-8"))
            selected_inputs = {
                Path(item["path"]).name: item["sha256"]
                for item in definition["curated_inputs"]
                if isinstance(item, dict) and isinstance(item.get("path"), str)
            }
            selected_new = source_names & set(selected_inputs)
            with self.subTest(seed_definition=path.name):
                if version < FIRST_ACCEPTED_SEED_VERSION:
                    self.assertEqual(selected_new, set())
                    continue
                if version < HISTORICAL_INCLUSION_SEED_VERSION:
                    self.assertEqual(
                        selected_new, initially_accepted_source_names
                    )
                    self.assertEqual(
                        {
                            name: selected_inputs[name]
                            for name in initially_accepted_source_names
                        },
                        initially_expected_inputs,
                    )
                    self.assertEqual(
                        definition["freshness_contract"][
                            "stale_inputs_excluded"
                        ],
                        [f"sources/{STALE_EXCLUDED_SOURCE_NAME}"],
                    )
                    continue
                self.assertEqual(selected_new, source_names)
                self.assertEqual(
                    {name: selected_inputs[name] for name in source_names},
                    historically_inclusive_inputs,
                )
                freshness = definition["freshness_contract"]
                self.assertNotIn(
                    f"sources/{STALE_EXCLUDED_SOURCE_NAME}",
                    freshness.get("stale_inputs_excluded", []),
                )
                self.assertIn(
                    f"sources/{STALE_EXCLUDED_SOURCE_NAME}",
                    freshness["historical_inputs_included_as_last_observed"],
                )

        snapshot = json.loads(
            (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        )
        self.assertEqual(snapshot["release_integration"], "none")
        self.assertEqual(snapshot["open_seed_integration"], "none")
        self.assertEqual(snapshot["downstream_product_integration"], "none")
        self.assertTrue(all(not item["seeded"] for item in snapshot["source_records"]))
        resolution = snapshot["resolution_review"]
        self.assertEqual(
            set(resolution["advisory_exact_targets_not_integrated"]),
            {"osm:way/106054206", "osm:way/1526491414"},
        )
        self.assertEqual(
            resolution["explicit_false_friend_excluded"], "osm:way/793888430"
        )
        self.assertEqual(
            set(resolution["generic_construction_candidates_excluded"]),
            {"osm:way/519414423", "osm:way/519414426"},
        )
        google_name = next(name for name in source_names if "saint-ghislain" in name)
        scala_name = next(name for name in source_names if "smextp01" in name)
        va4_name = next(name for name in source_names if "vantage-va4" in name)
        self.assertIsNone(documents[google_name]["campus"]["coordinates"])
        self.assertIsNone(documents[scala_name]["campus"]["coordinates"])
        self.assertEqual(
            documents[va4_name]["campus"]["coordinates"],
            {"latitude": 38.309875, "longitude": -77.466316},
        )

    def test_artifact_is_immutable_hash_bound_and_contains_no_raw_capture(self) -> None:
        self._validate_artifact(ARTIFACT)
        self.assertFalse(CAPTURE_DIRECTORY.exists())
        forbidden_suffixes = {
            ".body",
            ".headers",
            ".writeout",
            ".html",
            ".htm",
            ".pdf",
            ".txt",
        }
        self.assertEqual(
            [path for path in ARTIFACT.rglob("*") if path.suffix in forbidden_suffixes],
            [],
        )
        serialized = b"\n".join(
            path.read_bytes() for path in ARTIFACT.iterdir() if path.is_file()
        ).lower()
        for raw_marker in (
            b"<!doctype html",
            b"http/2 200",
            b"set-cookie:",
            b'"certs":',
            b"%pdf-",
        ):
            self.assertNotIn(raw_marker, serialized)

        snapshot = json.loads(
            (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        )
        records = {Path(item["path"]).name: item for item in snapshot["source_records"]}
        self.assertEqual(set(records), set(SOURCE_SPECS))
        for name, spec in SOURCE_SPECS.items():
            record = records[name]
            self.assertEqual(record["bytes"], spec["bytes"])
            self.assertEqual(record["sha256"], spec["sha256"])
            self.assertEqual(
                (record["current_status"], record["current_status_as_of_date"]),
                spec["latest"],
            )

    def test_source_capture_and_artifact_tampering_are_detected(self) -> None:
        originals = self._documents()
        kio_name = next(name for name in originals if "kio-mex8" in name)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            invalid_hash = copy.deepcopy(originals[kio_name])
            invalid_hash["evidence"][0]["content_hash"] = "not-a-sha256"
            invalid_path = root / "invalid-hash.json"
            self._write_document(invalid_path, invalid_hash)
            connection, _ = initialize(root / "invalid.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(
                    ValueError, "content_hash must be a lowercase SHA-256"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        invalid_path,
                        recorded_at=RECORDED_AT,
                    )
            finally:
                connection.close()

            weak_method = copy.deepcopy(originals[kio_name])
            weak_method["lifecycle"][0]["method"] = "authoritative_status_update"
            weak_path = root / "weak-method.json"
            self._write_document(weak_path, weak_method)
            connection, _ = initialize(root / "weak.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(
                    ValueError, "construction status requires"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        weak_path,
                        recorded_at=RECORDED_AT,
                    )
            finally:
                connection.close()

            future_capture = copy.deepcopy(originals[kio_name])
            future_capture["evidence"][0]["retrieved_at"] = "2026-07-22T00:00:00Z"
            future_path = root / "future-capture.json"
            self._write_document(future_path, future_capture)
            connection, _ = initialize(root / "future.sqlite")
            try:
                with self._offline(), self.assertRaisesRegex(
                    ValueError, "must not be later than the import recorded_at"
                ):
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        future_path,
                        recorded_at=RECORDED_AT,
                    )
            finally:
                connection.close()

            copied_artifact = root / "artifact"
            shutil.copytree(ARTIFACT, copied_artifact)
            inventory_path = copied_artifact / "retrieval-inventory.json"
            inventory_path.chmod(0o644)
            inventory_path.write_bytes(inventory_path.read_bytes() + b" ")
            with self.assertRaises(AssertionError):
                self._validate_artifact(copied_artifact, check_modes=False)

        leaked = copy.deepcopy(originals)
        leaked[kio_name]["capacities"].append(
            {
                "entity": "project",
                "metric": "critical_it_mw",
                "stage": "planned",
                "unit": "MW",
                "low": 4,
                "base": 4,
                "high": 4,
                "method": "reported",
                "confidence": 0.99,
                "evidence_key": leaked[kio_name]["evidence"][0]["key"],
                "as_of_date": "2026-03-09",
                "target_date": None,
                "notes": "Invalid typed leak from untyped capacity wording.",
            }
        )
        with self.assertRaises(AssertionError):
            self._assert_exact_semantics(leaked)

    def test_sources_import_offline_in_both_workspace_layouts(self) -> None:
        expected = {
            "capacity": 7,
            "entities": 14,
            "evidence": 19,
            "lifecycle": 8,
            "operating_models": 0,
            "snapshots": 14,
            "workloads": 0,
        }
        source_paths = [str(path) for path in self._source_paths()]
        for cwd, package in (
            (ROOT, "datacenter_atlas"),
            (WORKSPACE, "datacenter_atlas.datacenter_atlas"),
        ):
            with self.subTest(cwd=cwd):
                code = f"""
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import tempfile
from unittest.mock import patch
from {package}.curated_v11 import CuratedOfficialSourceAdapterV11
from {package}.database import initialize
from {package}.service import validate_database

sources = [Path(item) for item in {source_paths!r}]
with tempfile.TemporaryDirectory() as temporary:
    connection, _ = initialize(Path(temporary) / "atlas.sqlite")
    try:
        with ExitStack() as stack:
            error = AssertionError("network access")
            for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
                stack.enter_context(patch.object(socket, name, side_effect=error))
            for iteration in range(2):
                for source in sources:
                    result = CuratedOfficialSourceAdapterV11().import_file(
                        connection, source, recorded_at={RECORDED_AT!r}
                    )
                    assert result.warnings == ()
                    assert result.entities_created == (2 if iteration == 0 else 0)
        assert validate_database(connection) == []
        counts = {{
            "capacity": connection.execute("SELECT COUNT(*) FROM capacity_estimates").fetchone()[0],
            "entities": connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
            "evidence": connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0],
            "lifecycle": connection.execute("SELECT COUNT(*) FROM lifecycle_observations").fetchone()[0],
            "operating_models": connection.execute("SELECT COUNT(*) FROM operating_model_observations").fetchone()[0],
            "snapshots": connection.execute("SELECT COUNT(*) FROM entity_snapshots").fetchone()[0],
            "workloads": connection.execute("SELECT COUNT(*) FROM workload_observations").fetchone()[0],
        }}
        scala = connection.execute(
            "SELECT status, as_of_date FROM lifecycle_observations JOIN entities "
            "ON entities.id = lifecycle_observations.entity_id "
            "WHERE entities.stable_key = "
            "'curated:scala-smextp01-tepotzotlan-data-center:smextp01'"
        ).fetchone()
        assert tuple(scala) == ("operational", "2026-07-20")
        print(json.dumps(counts, sort_keys=True))
    finally:
        connection.close()
"""
                environment = {
                    **os.environ,
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": str(cwd),
                }
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    cwd=cwd,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), expected)


if __name__ == "__main__":
    unittest.main()
