from __future__ import annotations

import copy
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
from typing import Any
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
RECORDED_AT = "2026-07-21T03:40:00Z"
ARTIFACT = (
    ROOT
    / "source_artifacts"
    / "israel-official-five-projects-2026-07-20-v1"
)

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-20-israel-medone-ky1-kfar-yona.json": {
        "bytes": 12_376,
        "sha256": "ee16cdba9d19828e32384806c2a59836d390c26470867f1be9512689f4270424",
        "campus": "curated:israel-medone-kfar-yona-campus",
        "project": "curated:israel-medone-kfar-yona-campus:ky1",
        "evidence": 3,
        "lifecycle_dates": ("2026-02-24",),
        "capacity": (10.5, 10.5, 10.5, "2026-07-20"),
    },
    "curated-official-2026-07-20-israel-mega-mdcil1-modiin-phase-b.json": {
        "bytes": 9_025,
        "sha256": "3b8a95689406e24a26dc2e8ca6bdb6d6d10c2324fdc6e77b091c4ccb1fcf6830",
        "campus": "curated:israel-mega-dc-mdcil1-modiin-site",
        "project": "curated:israel-mega-dc-mdcil1-modiin-site:phase-b",
        "evidence": 2,
        "lifecycle_dates": ("2026-02-26", "2026-05-19"),
        "capacity": (9, 9, 9, "2026-05-19"),
    },
    "curated-official-2026-07-20-israel-mega-mdcil2-masmiyya-phase-a.json": {
        "bytes": 9_215,
        "sha256": "d390596c5e8371b89c0f632f426645cf098c55605f9940bceae4d98cc7c896ba",
        "campus": "curated:israel-mega-dc-mdcil2-masmiyya-site",
        "project": "curated:israel-mega-dc-mdcil2-masmiyya-site:phase-a",
        "evidence": 2,
        "lifecycle_dates": ("2026-02-26", "2026-05-19"),
        "capacity": (40, 40, 40, "2026-05-19"),
    },
    "curated-official-2026-07-20-israel-mega-mdcil4-beit-shemesh-phase-a.json": {
        "bytes": 9_297,
        "sha256": "365d02ff0a8078568249570fd2149aa65b2dd80309e354e6aabe1ff3f2cd3d4e",
        "campus": "curated:israel-mega-dc-mdcil4-beit-shemesh-site",
        "project": "curated:israel-mega-dc-mdcil4-beit-shemesh-site:phase-a",
        "evidence": 2,
        "lifecycle_dates": ("2026-02-26", "2026-05-19"),
        "capacity": (60, 60, 60, "2026-05-19"),
    },
    "curated-official-2026-07-20-israel-ned-levinstein-alfa-netanya-phase-a.json": {
        "bytes": 14_658,
        "sha256": "33d2cc327590ba2180fc0de3893f43e9ee6b939809f28aec1d11c3c12e8eb876",
        "campus": "curated:israel-ned-levinstein-alfa-netanya-campus",
        "project": "curated:israel-ned-levinstein-alfa-netanya-campus:phase-a",
        "evidence": 4,
        "lifecycle_dates": ("2026-03-01",),
        "capacity": (18, 18, 21, "2026-03-01"),
    },
}

ARTIFACT_FILE_SPECS = {
    "README.md": (
        3_080,
        "76d1fe4d4e41ee4d3e4d5b49022784096fdd1613f029d476f98367b23dbfa5a0",
    ),
    "manifest.json": (
        1_015,
        "a52244d9c504d326711f3e72daf30ab0720220fc2fd943b3cb7efca56bd92ff1",
    ),
    "manifest.sha256": (
        80,
        "9c0e73d85e7fc96ce73085cc14c8c52507b3759e76916c0fa96d5ada5260d4d6",
    ),
    "phase-boundaries.json": (
        4_077,
        "c9eb41e6456e67cadd84d67f11ce8a13f7262d704a2448a84a89cf2da138c9a9",
    ),
    "retrieval-inventory.json": (
        12_006,
        "b4ba92fdcef623032c0ce24589edd19a9ab72d6b07faf55c88da47451e373687",
    ),
    "rights-and-disposition.json": (
        2_623,
        "b448faaa05651183ed063f15152e2eaa7a0831cfcdb55cf717b252eef6ee51e7",
    ),
    "source-snapshot.json": (
        5_289,
        "afacf59924039da04a7850449e7dd0ba65df500d3ea980dcff306ea1c3233817",
    ),
}

CAPTURE_SPECS = {
    "ned_about": {
        "url": "https://www.ned-dc.com/about",
        "retrieved_at": "2026-07-21T03:34:17Z",
        "body": (
            137_262,
            "040e80e6e8ddac3cad251de57fc1e0600b3d4fba4c739f6c752357270db7b8bb",
        ),
        "headers": (
            692,
            "b14cd282f34b8df8ec087404ab9776461c46ea1d26d8166ab797ce90038a9e3f",
        ),
        "writeout": (
            10_655,
            "2a0da6a07feac619c6bf42fe0b19f155aea413c8a873eb3e4eeaa654ae9c0865",
        ),
        "http_version": "HTTP/1.1",
        "content_type": "text/html; charset=utf-8",
        "wire": 26_323,
    },
    "ned_netanya_i": {
        "url": "https://www.ned-dc.com/projects/?ContentID=70652",
        "retrieved_at": "2026-07-21T03:34:17Z",
        "body": (
            97_015,
            "e44f390b42ae4c8e147e2f7577d0546fe4c6c0372544ba994edd50cf990cca9e",
        ),
        "headers": (
            692,
            "844c37314ecf38a1f3e8fd541e30f58ec6d0c701f8d76babb28bec6ed4d6bf22",
        ),
        "writeout": (
            10_733,
            "6d3c98f1f916b71adef0dc06fb54d216845088c74b1f33171ca4761a57c4ca20",
        ),
        "http_version": "HTTP/1.1",
        "content_type": "text/html; charset=utf-8",
        "wire": 21_293,
    },
    "levinstein_march_presentation": {
        "url": "https://mayafiles.tase.co.il/rpdf/1730001-1731000/P1730405-00.pdf",
        "retrieved_at": "2026-07-21T03:34:17Z",
        "body": (
            10_308_159,
            "133d646ec9f8f440ecb38221aaa4f59da564cda8c004c366a1ccc36b69f24c07",
        ),
        "headers": (
            1_048,
            "7e914a288a8f2da56aa994a090539ee5a30d5a022a41695725f66202240b867e",
        ),
        "writeout": (
            18_387,
            "58699b2a5f27e9a587d41b7a3cd611c70fe0664c5219799d36accc6400eca638",
        ),
        "http_version": "HTTP/2",
        "content_type": "application/pdf",
        "wire": 10_308_159,
    },
    "levinstein_annual_report": {
        "url": "https://mayafiles.tase.co.il/rpdf/1730001-1731000/P1730141-00.pdf",
        "retrieved_at": "2026-07-21T03:34:16Z",
        "body": (
            5_088_779,
            "5624b4fc679f084a7f9a0b48567f7458843d162840b2b25402323f5ef527a6b6",
        ),
        "headers": (
            511,
            "95473124fd301fd790a343671f2d0f56eb65c3c437ce59d2416705222cfa30e2",
        ),
        "writeout": (
            18_380,
            "d26dccac9dd258b72eeca22ef77ca9ddba743de1496ab411a035ab8e26a8f2cd",
        ),
        "http_version": "HTTP/2",
        "content_type": "application/pdf",
        "wire": 5_088_779,
    },
    "mega_q1_report": {
        "url": "https://mayafiles.tase.co.il/rpdf/1742001-1743000/P1742528-00.pdf",
        "retrieved_at": "2026-07-21T03:34:16Z",
        "body": (
            5_230_897,
            "eb34d087de93c40477476470fdfd1e701438a4812a41a91b41ff81f98ce3dce3",
        ),
        "headers": (
            511,
            "ae53d431c8e261a3554f416f7426192c4d8c3137810d2f6e1bb73157234f5ebf",
        ),
        "writeout": (
            18_370,
            "155dffb86230cb546710f333a599e41b8164f3d02ad6c39ea8580dacd23aa0b8",
        ),
        "http_version": "HTTP/2",
        "content_type": "application/pdf",
        "wire": 5_230_897,
    },
    "mega_annual_report": {
        "url": (
            "https://megaor.co.il/wp-content/uploads/2026/05/"
            "%D7%93%D7%95%D7%97-%D7%AA%D7%A7%D7%95%D7%A4%D7%AA%D7%97-"
            "%D7%95%D7%A9%D7%A0%D7%AA%D7%99-%D7%9C%D7%A9%D7%A0%D7%AA-2025.pdf"
        ),
        "retrieved_at": "2026-07-21T03:34:17Z",
        "body": (
            9_029_494,
            "32da29360469f3ca2d13c5679fbff9bdbb2d5c2b423997c2f65a0522ecd4b5e2",
        ),
        "headers": (
            436,
            "54248fa163988f2efcc2087be3819bc87581211ee8cb5073f54db0dd99011c98",
        ),
        "writeout": (
            13_262,
            "937c70117d866a45f386fb491ce0867c7d83fc419bacd587300a358a6c40722c",
        ),
        "http_version": "HTTP/2",
        "content_type": "application/pdf",
        "wire": 9_029_494,
    },
    "medone_current_build": {
        "url": (
            "https://www.medone.co.il/articles/colocation-in-israel-why-medone-"
            "is-the-first-choice-for-mission-critical-infrastructure"
        ),
        "retrieved_at": "2026-07-21T03:34:17Z",
        "body": (
            78_797,
            "9ae3944b6acc9cef63e811ad80770bc282f75296064cce4dea7e0d6cb28fde5d",
        ),
        "headers": (
            1_478,
            "573655efc0b7b60a6951742d3cd70d9687c4a828c8008baa7750cacdc4bc4521",
        ),
        "writeout": (
            9_737,
            "73860b659a330b4890042a3e8a1465fda1aaab0c0c14ebe0a3ca8216069f47db",
        ),
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=utf-8",
        "wire": 28_443,
    },
    "medone_facilities": {
        "url": "https://medone.co.il/medonecloud/data-centers",
        "retrieved_at": "2026-07-21T03:34:17Z",
        "body": (
            97_776,
            "e998e50e57fc260b3db154d2f652ba9484435d840817bf69b3c367668119d77d",
        ),
        "headers": (
            1_400,
            "30ffeafdd3fde3d90ade5363c2da56a33e0b3e8d7c9a98b8f40dc0a0e0193910",
        ),
        "writeout": (
            9_513,
            "9f5739c7840a6f6f8a580bf42f05108c58dd79c960b6794c4c7e86574de4ec98",
        ),
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=utf-8",
        "wire": 26_184,
    },
    "medone_kfar_yona_build": {
        "url": (
            "https://www.medone.co.il/news-events/with-an-investment-of-more-than-"
            "one-billion-ils-medone-is-building-two-data-centers-in-kfar-yona"
        ),
        "retrieved_at": "2026-07-21T03:34:17Z",
        "body": (
            54_409,
            "a4fbb1ffc86713b1d9bea2775977f653884ea93044842a99610143fe5db37492",
        ),
        "headers": (
            1_429,
            "b4790e4070b24ee7a9763954198b407c04a6259bc98bfac74ea1440896f7e23e",
        ),
        "writeout": (
            9_787,
            "626ac2ec82e8b1871fcaef4793629a0a27a9fe9aae408ef7953e98847922e0b0",
        ),
        "http_version": "HTTP/2",
        "content_type": "text/html; charset=utf-8",
        "wire": 21_553,
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IsraelOfficialFiveProjectTests(unittest.TestCase):
    def _source_path(self, name: str) -> Path:
        return ROOT / "sources" / name

    def _load(self, name: str) -> dict[str, Any]:
        return json.loads(self._source_path(name).read_text(encoding="utf-8"))

    def _offline(self) -> ExitStack:
        stack = ExitStack()
        error = AssertionError("Israel curated import attempted network access")
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
        self, names: list[str], *, repetitions: int = 1
    ) -> tuple[tuple[tuple[Any, ...], ...], ...]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                with self._offline():
                    for repetition in range(repetitions):
                        for name in names:
                            result = CuratedOfficialSourceAdapterV11().import_file(
                                connection,
                                self._source_path(name),
                                recorded_at=RECORDED_AT,
                            )
                            self.assertEqual(result.warnings, ())
                            self.assertEqual(
                                result.entities_created,
                                2 if repetition == 0 else 0,
                            )
                            self.assertEqual(
                                result.evidence_created,
                                SOURCE_SPECS[name]["evidence"]
                                if repetition == 0
                                else 0,
                            )
                self.assertEqual(validate_database(connection), [])
                queries = (
                    "SELECT kind, stable_key, created_at FROM entities",
                    "SELECT json_extract(metadata_json, '$.curated_record_key'), "
                    "source_url, content_hash, retrieved_at FROM evidence",
                    "SELECT entities.stable_key, status, as_of_date, recorded_at, "
                    "method FROM lifecycle_observations JOIN entities "
                    "ON entities.id = lifecycle_observations.entity_id",
                    "SELECT entities.stable_key, as_of_date, method, latitude, "
                    "longitude, geometry_json FROM entity_snapshots JOIN entities "
                    "ON entities.id = entity_snapshots.entity_id",
                    "SELECT entities.stable_key, metric, stage, unit, low, base, "
                    "high, as_of_date, recorded_at, method FROM capacity_estimates "
                    "JOIN entities ON entities.id = capacity_estimates.entity_id",
                    "SELECT entity_id, operating_model "
                    "FROM operating_model_observations",
                    "SELECT entity_id, workload FROM workload_observations",
                )
                return tuple(
                    tuple(
                        sorted(
                            (tuple(row) for row in connection.execute(query)),
                            key=lambda row: json.dumps(row, ensure_ascii=False),
                        )
                    )
                    for query in queries
                )
            finally:
                connection.close()

    def _import_mutation(self, document: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            self._write_document(source, document)
            connection, _ = initialize(root / "atlas.sqlite")
            try:
                with self._offline():
                    CuratedOfficialSourceAdapterV11().import_file(
                        connection,
                        source,
                        recorded_at=RECORDED_AT,
                    )
            finally:
                connection.close()

    def test_sources_are_canonical_byte_pinned_schema_11_records(self) -> None:
        self.assertEqual(len(SOURCE_SPECS), 5)
        allowed_hosts = {
            "mayafiles.tase.co.il",
            "megaor.co.il",
            "medone.co.il",
            "www.medone.co.il",
            "www.ned-dc.com",
        }
        observed_projects: set[str] = set()
        for name, expected in SOURCE_SPECS.items():
            with self.subTest(source=name):
                source = self._source_path(name)
                self.assertTrue(source.is_file())
                self.assertFalse(source.is_symlink())
                self.assertTrue(stat.S_ISREG(source.stat().st_mode))
                self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o644)
                data = source.read_bytes()
                self.assertEqual(len(data), expected["bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected["sha256"])
                document = json.loads(data.decode("utf-8"))
                self.assertEqual(document["schema_version"], "1.1")
                self.assertEqual(document["campus"]["stable_key"], expected["campus"])
                self.assertEqual(document["project"]["stable_key"], expected["project"])
                observed_projects.add(document["project"]["stable_key"])
                for entity in (document["campus"], document["project"]):
                    self.assertEqual(entity["country"], "Israel")
                    self.assertEqual(entity["as_of_date"], "2026-07-20")
                    self.assertEqual(entity["roles"], {})
                    self.assertIsNone(entity["coordinates"])
                    self.assertIsNone(entity["geometry"])
                    self.assertEqual(entity["method"], "authoritative_locality")
                self.assertEqual(len(document["evidence"]), expected["evidence"])
                for evidence in document["evidence"]:
                    parsed = urlsplit(evidence["source_url"])
                    self.assertEqual(parsed.scheme, "https")
                    self.assertIn(parsed.hostname, allowed_hosts)
                    self.assertIsNone(parsed.username)
                    self.assertIsNone(parsed.password)
                    self.assertTrue(evidence["retrieved_at"].startswith("2026-07-21T"))
                    self.assertEqual(evidence["license"], "all-rights-reserved")
                    metadata = evidence["metadata"]
                    self.assertEqual(
                        metadata["capture_artifact_id"],
                        "israel-official-five-projects-2026-07-20-v1",
                    )
                    self.assertFalse(metadata["raw_response_retained"])
                    self.assertFalse(
                        metadata["raw_response_redistribution_permitted"]
                    )
                self.assertEqual(
                    tuple(item["as_of_date"] for item in document["lifecycle"]),
                    expected["lifecycle_dates"],
                )
                self.assertTrue(
                    all(
                        item["value"] == "under_construction"
                        and item["entity"] == "project"
                        and item["method"]
                        == "authoritative_physical_status_update"
                        for item in document["lifecycle"]
                    )
                )
                self.assertEqual(document["operating_models"], [])
                self.assertEqual(document["workloads"], [])
                self.assertEqual(len(document["capacities"]), 1)
                capacity = document["capacities"][0]
                self.assertEqual(capacity["entity"], "project")
                self.assertEqual(capacity["metric"], "critical_it_mw")
                self.assertEqual(capacity["stage"], "planned")
                self.assertEqual(capacity["unit"], "MW")
                self.assertEqual(capacity["method"], "reported")
                self.assertEqual(
                    (
                        capacity["low"],
                        capacity["base"],
                        capacity["high"],
                        capacity["as_of_date"],
                    ),
                    expected["capacity"],
                )
        self.assertEqual(observed_projects, {item["project"] for item in SOURCE_SPECS.values()})

    def test_capture_inventory_is_closed_exact_credential_free_and_hash_linked(self) -> None:
        inventory_text = (ARTIFACT / "retrieval-inventory.json").read_text(
            encoding="utf-8"
        )
        inventory = json.loads(inventory_text)
        self.assertEqual(
            inventory_text,
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(inventory["research_date"], "2026-07-20")
        self.assertEqual(inventory["direct_request_attempts"], 9)
        self.assertEqual(inventory["completed_response_requests"], 9)
        self.assertEqual(inventory["successful_http_requests"], 9)
        self.assertEqual(inventory["failed_http_requests"], 0)
        self.assertEqual(inventory["evidence_supporting_requests"], 9)
        self.assertFalse(inventory["request_credentials_supplied"])
        self.assertFalse(inventory["browser_session_used"])
        self.assertTrue(inventory["temporary_capture_directory_destroyed"])
        self.assertFalse(inventory["temporary_capture_recoverable"])
        self.assertFalse(inventory["raw_response_bodies_retained_in_artifact"])
        self.assertFalse(inventory["raw_response_headers_retained_in_artifact"])
        self.assertFalse(inventory["curl_writeouts_retained_in_artifact"])
        requests = {
            item["request_id"]: item for item in inventory["controlled_http_requests"]
        }
        self.assertEqual(set(requests), set(CAPTURE_SPECS))
        for request_id, expected in CAPTURE_SPECS.items():
            with self.subTest(capture=request_id):
                item = requests[request_id]
                self.assertEqual(item["requested_url"], expected["url"])
                self.assertEqual(item["effective_url"], expected["url"])
                self.assertEqual(item["retrieved_at"], expected["retrieved_at"])
                self.assertEqual(item["curl_exit_code"], 0)
                self.assertEqual(item["http_status"], 200)
                self.assertEqual(item["http_version"], expected["http_version"])
                self.assertEqual(item["content_type"], expected["content_type"])
                self.assertEqual(item["wire_download_bytes"], expected["wire"])
                self.assertEqual(
                    (item["body"]["bytes"], item["body"]["sha256"]),
                    expected["body"],
                )
                self.assertEqual(
                    (item["headers"]["bytes"], item["headers"]["sha256"]),
                    expected["headers"],
                )
                self.assertEqual(
                    (
                        item["curl_writeout"]["bytes"],
                        item["curl_writeout"]["sha256"],
                    ),
                    expected["writeout"],
                )
                self.assertFalse(item["body"]["retained_in_artifact"])
                self.assertFalse(item["headers"]["retained_in_artifact"])
                self.assertFalse(item["curl_writeout"]["retained_in_artifact"])

        used_captures: set[str] = set()
        for name in SOURCE_SPECS:
            for evidence in self._load(name)["evidence"]:
                capture_id = evidence["metadata"]["capture_request_id"]
                used_captures.add(capture_id)
                capture = requests[capture_id]
                self.assertEqual(evidence["source_url"], capture["requested_url"])
                self.assertEqual(evidence["retrieved_at"], capture["retrieved_at"])
                self.assertEqual(evidence["content_hash"], capture["body"]["sha256"])
                self.assertEqual(
                    evidence["metadata"]["capture_headers_sha256"],
                    capture["headers"]["sha256"],
                )
                self.assertEqual(
                    evidence["metadata"]["capture_curl_writeout_sha256"],
                    capture["curl_writeout"]["sha256"],
                )
        self.assertEqual(used_captures, set(CAPTURE_SPECS))

    def test_artifact_manifest_tree_modes_snapshot_and_no_raw_assets(self) -> None:
        self.assertEqual(
            {path.name for path in ARTIFACT.iterdir() if path.is_file()},
            set(ARTIFACT_FILE_SPECS),
        )
        for name, (expected_bytes, expected_hash) in ARTIFACT_FILE_SPECS.items():
            path = ARTIFACT / name
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(len(path.read_bytes()), expected_bytes)
            self.assertEqual(sha256(path), expected_hash)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertNotIn(b"%PDF-", path.read_bytes())
            self.assertNotIn(b"<!DOCTYPE html", path.read_bytes())

        manifest_text = (ARTIFACT / "manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
        self.assertEqual(
            manifest_text,
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        )
        self.assertEqual(
            (ARTIFACT / "manifest.sha256").read_text(encoding="utf-8"),
            f"{ARTIFACT_FILE_SPECS['manifest.json'][1]}  manifest.json\n",
        )
        self.assertEqual(
            {item["path"] for item in manifest["files"]},
            {
                "README.md",
                "phase-boundaries.json",
                "retrieval-inventory.json",
                "rights-and-disposition.json",
                "source-snapshot.json",
            },
        )
        for item in manifest["files"]:
            path = ARTIFACT / item["path"]
            self.assertEqual(len(path.read_bytes()), item["bytes"])
            self.assertEqual(sha256(path), item["sha256"])
        tree_payload = json.dumps(manifest["files"], indent=2, sort_keys=True) + "\n"
        self.assertEqual(
            hashlib.sha256(tree_payload.encode()).hexdigest(),
            manifest["tree_sha256"],
        )

        snapshot = json.loads(
            (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        )
        self.assertEqual(snapshot["package_state"], "standalone_unseeded")
        self.assertEqual(snapshot["release_integration"], "none")
        self.assertEqual(snapshot["open_seed_integration"], "none")
        self.assertEqual(snapshot["totals"]["source_records"], 5)
        self.assertEqual(snapshot["totals"]["controlled_http_captures"], 9)
        self.assertEqual(snapshot["totals"]["lifecycle_observations"], 8)
        self.assertEqual(snapshot["totals"]["capacity_estimates"], 5)
        records = {Path(item["path"]).name: item for item in snapshot["source_records"]}
        self.assertEqual(set(records), set(SOURCE_SPECS))
        for name, expected in SOURCE_SPECS.items():
            item = records[name]
            source = self._source_path(name)
            self.assertEqual(item["bytes"], len(source.read_bytes()))
            self.assertEqual(item["sha256"], sha256(source))
            self.assertEqual(item["project_stable_key"], expected["project"])
            self.assertFalse(item["coordinates_present"])
            self.assertFalse(item["geometry_present"])
            self.assertFalse(item["seeded"])

    def test_phase_and_rights_boundaries_are_closed(self) -> None:
        boundaries = json.loads(
            (ARTIFACT / "phase-boundaries.json").read_text(encoding="utf-8")
        )
        decisions = {item["project_stable_key"]: item for item in boundaries["decisions"]}
        self.assertEqual(decisions, {
            expected["project"]: decisions[expected["project"]]
            for expected in SOURCE_SPECS.values()
        })
        self.assertTrue(boundaries["metric_rules"]["normalized_values_must_be_explicitly_typed_it"])
        self.assertTrue(boundaries["metric_rules"]["mva_metadata_only"])
        self.assertTrue(boundaries["metric_rules"]["area_metadata_only"])
        self.assertFalse(boundaries["metric_rules"]["annual_energy_derived"])
        self.assertFalse(boundaries["metric_rules"]["pue_derived"])
        self.assertFalse(boundaries["metric_rules"]["point_coordinates_allowed"])
        normalized_projects = " ".join(decisions).lower()
        self.assertNotIn("ky2", normalized_projects)
        self.assertNotIn("mdcil4-beit-shemesh-site:phase-b", normalized_projects)

        rights = json.loads(
            (ARTIFACT / "rights-and-disposition.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            rights["rights_posture"], "no_source_material_redistribution"
        )
        for group in rights["source_groups"]:
            self.assertFalse(group["affirmative_open_reuse_license_found"])
        disposition = rights["disposition"]
        for field in (
            "raw_response_bodies_retained_in_repository",
            "raw_response_headers_retained_in_repository",
            "curl_writeouts_retained_in_repository",
            "page_renders_retained_in_repository",
            "text_extractions_retained_in_repository",
            "publisher_media_retained_in_repository",
            "private_raw_source_cache_retained",
        ):
            self.assertFalse(disposition[field])
        self.assertTrue(disposition["temporary_capture_directory_destroyed_after_verification"])

    def test_import_is_offline_idempotent_order_independent_and_valid(self) -> None:
        names = list(SOURCE_SPECS)
        forward = self._database_state(names, repetitions=2)
        reverse = self._database_state(list(reversed(names)))
        self.assertEqual(forward, reverse)
        self.assertEqual(len(forward[0]), 10)
        self.assertEqual(len(forward[1]), 13)
        self.assertEqual(len(forward[2]), 8)
        self.assertEqual(len(forward[3]), 10)
        self.assertEqual(len(forward[4]), 5)
        self.assertEqual(forward[5], ())
        self.assertEqual(forward[6], ())
        self.assertTrue(all(row[3] == RECORDED_AT for row in forward[2]))
        self.assertTrue(all(row[8] == RECORDED_AT for row in forward[4]))
        self.assertTrue(all(row[1] == "critical_it_mw" for row in forward[4]))
        self.assertTrue(all(row[2] == "planned" for row in forward[4]))
        self.assertTrue(all(row[3] == "MW" for row in forward[4]))
        self.assertTrue(all(row[3:6] == (None, None, None) for row in forward[3]))

    def test_adversarial_mutations_fail_closed_offline(self) -> None:
        base = self._load(
            "curated-official-2026-07-20-israel-medone-ky1-kfar-yona.json"
        )
        mutations: list[tuple[str, dict[str, Any], str]] = []

        future = copy.deepcopy(base)
        future["evidence"][0]["retrieved_at"] = "2026-07-21T03:40:01Z"
        mutations.append(("post-transaction evidence", future, "retrieved_at"))

        missing_evidence = copy.deepcopy(base)
        missing_evidence["capacities"][0]["evidence_key"] = "missing"
        mutations.append(("missing evidence reference", missing_evidence, "missing"))

        duplicate_lifecycle = copy.deepcopy(base)
        duplicate_lifecycle["lifecycle"].append(
            copy.deepcopy(duplicate_lifecycle["lifecycle"][0])
        )
        mutations.append(("duplicate lifecycle claim", duplicate_lifecycle, "duplicate"))

        inverted = copy.deepcopy(base)
        inverted["capacities"][0]["low"] = 11
        mutations.append(("inverted capacity range", inverted, "low <= base"))

        measured_energy = copy.deepcopy(base)
        measured_energy["capacities"][0].update(
            {
                "metric": "annual_energy_mwh",
                "stage": "measured",
                "unit": "MWh/year",
            }
        )
        mutations.append(
            (
                "company disclosure measured energy",
                measured_energy,
                "measured annual energy",
            )
        )

        bad_coordinate = copy.deepcopy(base)
        bad_coordinate["campus"]["coordinates"] = {
            "latitude": 91,
            "longitude": 34,
        }
        mutations.append(
            (
                "authoritative-locality coordinate injection",
                bad_coordinate,
                "requires null coordinates",
            )
        )

        for label, document, message in mutations:
            with self.subTest(mutation=label):
                with self.assertRaisesRegex(ValueError, message):
                    self._import_mutation(document)


if __name__ == "__main__":
    unittest.main()
