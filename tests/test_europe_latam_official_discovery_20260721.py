from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas.curated_v11 import CuratedOfficialSourceAdapterV11
from datacenter_atlas.database import initialize
from datacenter_atlas import europe_latam_official_discovery_temporal_v2 as correction
from datacenter_atlas.service import validate_database


ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "source_artifacts/europe-latam-official-discovery-2026-07-21-v1"
INCIDENT = ROOT / "source_artifacts/europe-latam-official-discovery-temporal-incident-2026-07-21-v1"
V2 = ROOT / "source_artifacts/europe-latam-official-discovery-2026-07-21-v2"
TRASH = Path("/Users/kian/.Trash/dc-europe-latam-official-20260721.eA43A2")
RECORDED_AT = "2026-07-21T10:02:31Z"

V1_FILES = {
    "README.md": (2379, "82f947edcebd15f9c9cdbf3f9b4c0e8e5728a3dbcb12d1517df6c512acea3453"),
    "identity-and-capacity-guardrails.json": (2571, "26bbe24475261fa28ddc0182371ee278ed9edc72effbe36e88f6dd9e3cf5527e"),
    "manifest.json": (1569, "af62e982f6cc4522a87e3717b0a7ae86ef19d3cc0616af393a83de4921093cdc"),
    "manifest.sha256": (80, "03dd10030c89e36dda0445c07725a68e7bd17f8ed462a9213aeb2a2346677344"),
    "retrieval-inventory.json": (6313, "21d34594bd0fe18b451acee0d5790d364a0ea5c4b4865e2c4fe661a445a1e74c"),
    "rights-and-disposition.json": (1256, "25dea8c38d5f61fb3006d62d601413ce417b6d8bd47dbf8785865e8220559e1d"),
    "source-snapshot.json": (7808, "af7b62744238f0455e3c59297b634c1d5bf3ff69b3a3390da811ac6b2b6c6262"),
}

INCIDENT_FILES = {
    "README.md": (1130, "f556d6679cb8575243b26876d05acf527950176ea2fdbe618dfb772448226f01"),
    "incident.json": (3928, "4209a57504a0cf104d0964de700cc9b0c8b175782c56f83568e8e89208a9cfc8"),
    "manifest.json": (827, "d0f30bad34c57b0336816294306852e595ad08e1090ff1f1e25912efb8633a2a"),
    "manifest.sha256": (80, "944c557945cc0f36cd952e358ff4ce17716d9f750317df91693a9151e5544cd0"),
}

V2_FILES = {
    "README.md": (1405, "142c9e4c21b013a8b0415b9e26ed7f0e7a9f85935301f0a4cbffd7d5bf10916a"),
    "identity-and-capacity-guardrails.json": (3172, "0f0158f1c4be8d11ebd06868faf765cf33ddf34f9c2feec42e39e7eb2f8343aa"),
    "manifest.json": (2237, "8e5eb78bd273bdbe9521ba7ef52f60bb9b4eab89d8d208c9fef6569aecba313c"),
    "manifest.sha256": (80, "f4ca842e5d2e199ad06683e01ee2128707efd983b55e3f7d0a3cac6214fec7c8"),
    "retrieval-inventory.json": (7436, "b94fbbe6e76dde8389c7acb9d67c6bbd3c4a282eb9ce18e771e303c5607c6ee9"),
    "rights-and-disposition.json": (1670, "5783931baa57b4fa8d838f628aac9be35e09164dc46a42e931d7343c469e3cfe"),
    "source-snapshot.json": (9104, "7e7bea36a6cdadf398dd83524e05c7f8ff0bee495f094c863d0fe1ae6809f65a"),
}

SOURCE_PAIRS = {
    "curated-official-2026-07-21-arnes-maribor-construction-start-v2.json": {
        "v2": (10571, "672db6db061157f19c55691cf5ce84668a149d1f7bc5be6dcb8607c4e901e52b"),
        "v1_name": "curated-official-2026-07-21-arnes-maribor-construction-start.json",
        "v1": (8971, "24be5cec5cdb1df39a4287a65e39f41053bc40976a06fa77fa45be3a717d6dac"),
    },
    "curated-official-2026-07-21-kio-second-guatemala-construction-start-v2.json": {
        "v2": (8402, "10e17a3fb0619031a124dc3f58800b3b51c6a43671b071a4f5363d4558eb95fc"),
        "v1_name": "curated-official-2026-07-21-kio-second-guatemala-construction-start.json",
        "v1": (7862, "5265afc6c6c3ed8947eee54de73f31328accd1badf513500b39acf65278bad4f"),
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


class EuropeLatamTemporalCorrectionTests(unittest.TestCase):
    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("temporal-correction replay attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def _assert_frozen_pins(
        self, bundle: Path, expected: dict[str, tuple[int, str]]
    ) -> None:
        self.assertTrue(bundle.is_dir())
        self.assertFalse(bundle.is_symlink())
        self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o555)
        self.assertEqual({path.name for path in bundle.iterdir()}, set(expected))
        for name, pin in expected.items():
            path = bundle / name
            self.assertFalse(path.is_symlink())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o444)
            self.assertEqual((len(path.read_bytes()), sha256(path)), pin)
            if path.suffix == ".json":
                raw = path.read_bytes()
                self.assertEqual(
                    raw,
                    (json.dumps(json.loads(raw), indent=2, ensure_ascii=False) + "\n").encode(),
                )

    def test_v1_is_byte_exact_but_explicitly_nonaccepted(self) -> None:
        self._assert_frozen_pins(V1, V1_FILES)
        self.assertEqual(
            correction.tree_digest(V1),
            "4f3fa8d9aaa79d0c30b858df9d33fb0a51c0653e63638f498161a1fb28d8c53c",
        )
        for spec in SOURCE_PAIRS.values():
            path = ROOT / "sources" / spec["v1_name"]
            self.assertEqual((len(path.read_bytes()), sha256(path)), spec["v1"])
        incident = json.loads((INCIDENT / "incident.json").read_text())
        subjects = {row["path"]: row for row in incident["subjects"]}
        self.assertEqual(len(subjects), 3)
        for path in (
            "source_artifacts/europe-latam-official-discovery-2026-07-21-v1",
            "sources/curated-official-2026-07-21-arnes-maribor-construction-start.json",
            "sources/curated-official-2026-07-21-kio-second-guatemala-construction-start.json",
        ):
            self.assertEqual(subjects[path]["acceptance_status"], "non_accepted")
            self.assertEqual(subjects[path]["disposition"], "rejected_preserved")

    def test_incident_and_v2_are_frozen_canonical_and_exact(self) -> None:
        self._assert_frozen_pins(INCIDENT, INCIDENT_FILES)
        self._assert_frozen_pins(V2, V2_FILES)
        self.assertEqual(
            correction.tree_digest(INCIDENT),
            "ba9ee8e249abfb19e4496c9e19ab264af839014d722ba7875b4e7176cebda8be",
        )
        self.assertEqual(
            correction.tree_digest(V2),
            "3f0af347eae593b9f60df765910be4d6523efc0c66b2b59cd7a201b5cb49fa32",
        )
        manifest = json.loads((V2 / "manifest.json").read_text())
        self.assertEqual(manifest["recorded_at"], RECORDED_AT)
        self.assertEqual(manifest["acceptance_status"], "accepted_temporal_successor")
        predecessor = manifest["supersedes_non_accepted_origin"]
        self.assertEqual(predecessor["artifact_id"], V1.name)
        self.assertEqual(
            predecessor["incident_manifest_sha256"], INCIDENT_FILES["manifest.json"][1]
        )
        self.assertEqual(manifest["release_integration"], "none")
        self.assertEqual(manifest["open_seed_integration"], "none")
        self.assertEqual(manifest["downstream_product_integration"], "none")

    def test_completed_writeout_mtime_not_birth_controls_retrieved_at(self) -> None:
        inventory = json.loads((V2 / "retrieval-inventory.json").read_text())
        rows = {row["request_id"]: row for row in inventory["controlled_http_requests"]}
        expected = {
            "arnes_government_start": (
                "2026-07-21T09:47:50Z",
                "2026-07-21T09:47:47Z",
                "2026-07-21T09:47:50Z",
                "2026-07-21T09:47:48Z",
            ),
            "arnes_project_page": (
                "2026-07-21T09:47:51Z",
                "2026-07-21T09:47:50Z",
                "2026-07-21T09:47:52Z",
                "2026-07-21T09:47:50Z",
            ),
            "kio_gtm2_start": (
                "2026-07-21T09:47:52Z",
                "2026-07-21T09:47:52Z",
                "2026-07-21T09:47:52Z",
                "2026-07-21T03:57:50Z",
            ),
        }
        for request_id, (
            body_birth,
            writeout_birth,
            completed_at,
            server_date,
        ) in expected.items():
            row = rows[request_id]
            self.assertEqual(row["capture_body_birth_utc"], body_birth)
            self.assertEqual(row["capture_writeout_birth_utc"], writeout_birth)
            self.assertEqual(row["capture_writeout_mtime_utc"], completed_at)
            self.assertEqual(row["retrieval_completed_at"], completed_at)
            self.assertEqual(row["retrieved_at"], completed_at)
            self.assertEqual(row["response_http_date"], server_date)
            self.assertFalse(row["response_http_date_used_as_retrieved_at"])
            writeout = TRASH / f"{request_id}.writeout"
            actual_completed = datetime.fromtimestamp(
                writeout.stat().st_mtime, timezone.utc
            ).replace(microsecond=0)
            self.assertEqual(instant(completed_at), actual_completed)
        self.assertNotEqual(
            rows["arnes_project_page"]["capture_body_birth_utc"],
            rows["arnes_project_page"]["retrieved_at"],
        )
        self.assertNotEqual(
            rows["arnes_project_page"]["capture_writeout_birth_utc"],
            rows["arnes_project_page"]["retrieved_at"],
        )

    def test_birth_as_completion_mutation_is_rejected(self) -> None:
        name = "curated-official-2026-07-21-arnes-maribor-construction-start-v2.json"
        document = json.loads((ROOT / "sources" / name).read_text())
        mutated = deepcopy(document)
        project_evidence = next(
            row
            for row in mutated["evidence"]
            if row["metadata"]["capture_request_id"] == "arnes_project_page"
        )
        project_evidence["retrieved_at"] = project_evidence["metadata"][
            "capture_body_birth_utc"
        ]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / name
            path.write_text(
                json.dumps(mutated, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "retrieval completion differs"):
                correction._validate_source_successor(path, name)

    def test_source_successors_change_temporal_metadata_only(self) -> None:
        correction._validate_source_collisions()
        for name, spec in SOURCE_PAIRS.items():
            v2_path = ROOT / "sources" / name
            v1_path = ROOT / "sources" / spec["v1_name"]
            self.assertEqual((len(v2_path.read_bytes()), sha256(v2_path)), spec["v2"])
            self.assertEqual((len(v1_path.read_bytes()), sha256(v1_path)), spec["v1"])
            self.assertEqual(stat.S_IMODE(v2_path.stat().st_mode), 0o644)
            v2_document = json.loads(v2_path.read_text())
            v1_document = json.loads(v1_path.read_text())
            self.assertEqual(
                correction._semantic_source(v2_document),
                correction._semantic_source(v1_document),
            )
            for evidence in v2_document["evidence"]:
                timing = correction.CAPTURE_TIMES[
                    evidence["metadata"]["capture_request_id"]
                ]
                self.assertEqual(evidence["retrieved_at"], timing["completed_at"])
                self.assertEqual(
                    evidence["metadata"]["retrieval_timestamp_basis"],
                    "UTC whole-second mtime of the completed curl writeout, sampled after curl returned",
                )

    def test_v2_sources_import_offline_idempotently_with_exact_claims(self) -> None:
        with self._offline(), tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            adapter = CuratedOfficialSourceAdapterV11()
            for _ in range(2):
                for name in SOURCE_PAIRS:
                    adapter.import_file(
                        connection,
                        ROOT / "sources" / name,
                        recorded_at=RECORDED_AT,
                    )
            validate_database(connection)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0], 4
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 3
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM lifecycle_observations"
                ).fetchone()[0],
                2,
            )
            capacities = connection.execute(
                "SELECT metric, stage, unit, base FROM capacity_estimates ORDER BY metric"
            ).fetchall()
            self.assertEqual(
                [tuple(row) for row in capacities],
                [
                    ("critical_it_mw", "design", "MW", 2.0),
                    ("pue", "design", "ratio", 1.5),
                ],
            )

    def test_offline_replay_real_timestamp_and_no_integration(self) -> None:
        before = datetime.now(timezone.utc)
        with self._offline():
            incident_manifest = correction.validate_incident(INCIDENT)
            v2_manifest = correction.validate_v2_artifact(V2)
        after = datetime.now(timezone.utc)
        self.assertEqual(incident_manifest["recorded_at"], RECORDED_AT)
        self.assertEqual(v2_manifest["recorded_at"], RECORDED_AT)
        recorded_at = instant(RECORDED_AT)
        for bundle in (INCIDENT, V2):
            birth = datetime.fromtimestamp(bundle.stat().st_birthtime, timezone.utc)
            self.assertLessEqual(birth, recorded_at)
        self.assertLessEqual(recorded_at, before)
        self.assertLessEqual(recorded_at, after)
        snapshot = json.loads((V2 / "source-snapshot.json").read_text())
        for key in (
            "release_integration",
            "open_seed_integration",
            "construction_timeline_integration",
            "federation_integration",
            "identity_integration",
            "coordinate_integration",
            "coverage_ledger_integration",
            "downstream_product_integration",
        ):
            self.assertEqual(snapshot[key], "none")
        self.assertEqual(snapshot["totals"]["current_status_unknown"], 2)
        definition = json.loads(
            (ROOT / "sources/open-seed-2026-07-21-v69.json").read_text()
        )
        selected = {row["path"] for row in definition["curated_inputs"]}
        self.assertTrue(
            selected.isdisjoint({f"sources/{name}" for name in SOURCE_PAIRS})
        )

    def test_raw_capture_unchanged_and_existing_outputs_are_no_replace(self) -> None:
        correction._validate_raw_capture()
        before = {
            "v1": correction.tree_digest(V1),
            "incident": correction.tree_digest(INCIDENT),
            "v2": correction.tree_digest(V2),
            "sources": {
                name: sha256(ROOT / "sources" / name) for name in SOURCE_PAIRS
            },
        }
        with self.assertRaisesRegex(
            SystemExit, "correction output already exists; refusing replacement"
        ):
            correction.build()
        after = {
            "v1": correction.tree_digest(V1),
            "incident": correction.tree_digest(INCIDENT),
            "v2": correction.tree_digest(V2),
            "sources": {
                name: sha256(ROOT / "sources" / name) for name in SOURCE_PAIRS
            },
        }
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
