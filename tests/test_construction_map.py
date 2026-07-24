from __future__ import annotations

from collections import Counter
from copy import deepcopy
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from datacenter_atlas.construction_map import (
    ConstructionMapError,
    DEFAULT_VISIBLE_TIERS,
    FIELDS,
    MAP_SCOPE,
    STRICT_DEFINITION_ROLE,
    _operating_model,
    build_index,
    is_frozen_map,
    validate_construction_map,
    validate_map_definition,
    write_construction_map,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V3_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-map-2026-07-18-public-open-v3.json"
)
V3_MASTER_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-master-2026-07-18-public-open-v3.json"
)
V3_MASTER = PROJECT_ROOT / "construction_master" / "2026-07-18-public-open-v3"
V3_MAP = PROJECT_ROOT / "construction_maps" / "2026-07-18-public-open-v3"
V4_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-map-2026-07-18-public-open-v4.json"
)
V4_MASTER_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-master-2026-07-18-public-open-v4.json"
)
V4_MASTER = PROJECT_ROOT / "construction_master" / "2026-07-18-public-open-v4"
V4_MAP = PROJECT_ROOT / "construction_maps" / "2026-07-18-public-open-v4"
V5_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-map-2026-07-18-public-open-v5.json"
)
V5_MASTER_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-master-2026-07-18-public-open-v5.json"
)
V5_MASTER = PROJECT_ROOT / "construction_master" / "2026-07-18-public-open-v5"
V5_MAP = PROJECT_ROOT / "construction_maps" / "2026-07-18-public-open-v5"
V6_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-map-2026-07-19-public-open-v6.json"
)
V6_MASTER_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-master-2026-07-19-public-open-v6.json"
)
V6_MASTER = PROJECT_ROOT / "construction_master" / "2026-07-19-public-open-v6"
V6_MAP = PROJECT_ROOT / "construction_maps" / "2026-07-19-public-open-v6"
V7_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-map-2026-07-19-public-open-v7.json"
)
V7_MASTER_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-master-2026-07-19-public-open-v7.json"
)
V7_MASTER = PROJECT_ROOT / "construction_master" / "2026-07-19-public-open-v7"
V7_MAP = PROJECT_ROOT / "construction_maps" / "2026-07-19-public-open-v7"
V8_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-map-2026-07-19-public-open-v8.json"
)
V8_MASTER_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-master-2026-07-19-public-open-v8.json"
)
V8_MASTER = PROJECT_ROOT / "construction_master" / "2026-07-19-public-open-v8"
V8_MAP = PROJECT_ROOT / "construction_maps" / "2026-07-19-public-open-v8"
V9_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-map-2026-07-19-public-open-v9.json"
)
V9_MASTER_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-master-2026-07-19-public-open-v9.json"
)
V9_MASTER = PROJECT_ROOT / "construction_master" / "2026-07-19-public-open-v9"
V9_MAP = PROJECT_ROOT / "construction_maps" / "2026-07-19-public-open-v9"
V10_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-map-2026-07-19-public-open-v10.json"
)
V10_MASTER_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-master-2026-07-19-public-open-v10.json"
)
V10_MASTER = PROJECT_ROOT / "construction_master" / "2026-07-19-public-open-v10"
V10_MAP = PROJECT_ROOT / "construction_maps" / "2026-07-19-public-open-v10"
V11_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-map-2026-07-19-public-open-v11.json"
)
V11_MASTER_DEFINITION = (
    PROJECT_ROOT / "sources" / "construction-master-2026-07-19-public-open-v11.json"
)
V11_MASTER = PROJECT_ROOT / "construction_master" / "2026-07-19-public-open-v11"
V11_MAP = PROJECT_ROOT / "construction_maps" / "2026-07-19-public-open-v11"
V7_MAP_BUNDLE_INVENTORY_SHA256 = (
    "c53fd100ad66651fa6399e009cb4d04c1c766bd82fa00415f088523f51dd7269"
)
V8_MAP_BUNDLE_INVENTORY_SHA256 = (
    "9764a0ce1d0a8325cd28d50c04c1fd87d00048116c0bea4dbb1640a601e74c6f"
)
V9_MAP_BUNDLE_INVENTORY_SHA256 = (
    "7a13525f8051e89d1e4ad1e3a41d8d5a5d11af02aef661e411cc89dea8611cd1"
)
V10_MAP_BUNDLE_INVENTORY_SHA256 = (
    "7df2f0e6ce33152273388a9fa03f808901ffc3a4b52a4835fdc6b1a0724f76db"
)
V11_MAP_BUNDLE_INVENTORY_SHA256 = (
    "e1d0bc6f9f957a6bd2164b6566dbf2a90473193d7acd7d1ed62bab88f8c506dd"
)
V9_ADDITION_IDS = {
    "1d95d387-1806-5dda-a619-a50e84852137",
    "27f804d6-f887-51a3-9564-4e738793d2f8",
    "296ce9ca-8904-5976-9226-aa9ee6b9ae70",
    "55f4eb88-750d-5aa5-b4cb-bd5b8e746fe6",
    "6564e429-77a5-5548-a5b0-ec6f2a402d47",
    "6e05e286-dbad-5550-900d-ed0c2294e5a2",
    "7206a400-093d-5c92-b1c5-c4243807de29",
    "7d936c4e-29f2-592f-984b-61f5d6367fc8",
    "9c96ba2a-1e05-53b4-a7bb-86057ddcba1f",
    "b7744ad5-aa48-5977-a70e-3d6a588f468d",
    "bdfd522f-2d7e-5d1f-8e00-3c43b462ed27",
    "c6c50c6d-b3b3-5e33-bed0-4da5b6372a9b",
    "c73ac912-e44d-5477-84f5-c5beb4813518",
}
LEGACY_BUNDLE_INVENTORY_SHA256 = {
    "v1": "29449fabe9ad80c5029476b28652da16096d368fa119391bc9f1c74f30dd1598",
    "v2": "ed2aa47286f48ffb882d8decd61f6bceb28ab830f010592f67fc424beba64f4b",
    "v3": "5f9b67e1ac484900ab71924b5ae8bd4f3b05c554227c9a39fdb0d479031d1a60",
    "v4": "1539d9c97dedbe7d93c9e76c620c849b416e32d57e019d671966abc1ee09e87d",
    "v5": "8bffb1858633584fc41f3b49b93fc4ffafeac37ede3503f0ed7110458a4aa77c",
    "v6": "ba6c04777d434ba44be0f3e3692a7869625889589f9db73d5182bc074a04b8ad",
}


def _row(*, row_id: str = "row-1", tier: str = "A", latitude=1.5, longitude=2.5):
    return {
        "annual_energy_observations": [],
        "capacity_observations": [
            {
                "confidence": 0.5,
                "high": 12,
                "low": 8,
                "method": "source_reported",
                "metric": "gross_facility_mw",
                "stage": "planned",
                "target_date": None,
                "unit": "MW",
                "value": 10,
            }
        ],
        "construction": {
            "confidence": 0.5,
            "source_supported": tier == "A",
            "verification_status": "source_supported_not_independently_verified",
            "verified": False,
        },
        "disposition": {"label": "review_only" if tier != "A" else "included"},
        "entity": {
            "address": "1 Example Road",
            "country": "Exampleland",
            "country_iso_a3": "EXP",
            "kind": "project",
            "latitude": latitude,
            "longitude": longitude,
            "name": "Example </script> campus",
        },
        "evidence_scope": "source_observation",
        "first_evidence_date": "2026-01-01",
        "identity": {"status": "source_scoped"},
        "last_evidence_date": "2026-07-18",
        "lifecycle": {
            "normalized_status": "under_construction" if tier == "A" else "review_lead",
            "reported_status": "building",
            "reported_status_date": "2026-07-18",
        },
        "observation_kind": "source_construction_pipeline" if tier == "A" else "review_lead",
        "operating_model_observation": None,
        "pue_observations": [],
        "resolution_advisories": [],
        "review_only": tier != "A",
        "row_id": row_id,
        "satellite_links": [],
        "source": {
            "artifact_id": "fixture",
            "record_id": row_id,
            "release_id": "fixture-v1",
            "source_license": "CC-BY-4.0",
            "source_url": "https://example.test/source",
        },
        "source_evidence": [{"publisher": "Fixture Publisher"}],
        "tier": tier,
        "untyped_capacity_statements": [],
        "workload_observations": [],
    }


def _master_fixture(root: Path) -> tuple[Path, Path]:
    master = root / "master"
    master.mkdir()
    rows = [_row(), _row(row_id="row-2", tier="B", latitude=None, longitude=None)]
    raw = b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for row in rows
    )
    (master / "construction-master.jsonl").write_bytes(raw)
    manifest = {
        "generated_at": "2026-07-18T00:00:00Z",
        "master_id": "fixture-master-v1",
        "outputs": {
            "construction-master.jsonl": {
                "bytes": len(raw),
                "records": 2,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        },
        "row_counts": {"total": 2},
    }
    manifest_raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (master / "manifest.json").write_bytes(manifest_raw)
    definition = root / "unused-definition.json"
    definition.write_text("{}\n", encoding="utf-8")
    return master, definition


def _bundle_inventory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        digest.update(entry.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(entry.read_bytes()).digest())
    return digest.hexdigest()


class ConstructionMapTests(unittest.TestCase):
    def test_index_preserves_tier_and_skips_only_fully_missing_coordinates(self) -> None:
        manifest = {
            "generated_at": "2026-07-18T00:00:00Z",
            "master_id": "fixture",
            "row_counts": {"total": 2},
        }
        index, coverage = build_index(
            [_row(), _row(row_id="missing", tier="B", latitude=None, longitude=None)],
            master_manifest=manifest,
            master_manifest_sha256="a" * 64,
        )
        self.assertEqual(index["fields"], list(FIELDS))
        self.assertEqual(len(index["rows"]), 1)
        projected = dict(zip(FIELDS, index["rows"][0], strict=True))
        self.assertEqual(projected["tier"], "A")
        self.assertFalse(projected["construction_verified"])
        self.assertEqual(coverage["counts"]["master_observation_rows"], 2)
        self.assertEqual(coverage["counts"]["unmapped_observation_rows"], 1)
        self.assertIsNone(coverage["counts"]["unique_physical_site_count"])

    def test_operating_model_projects_canonical_master_value(self) -> None:
        self.assertEqual(
            _operating_model(
                {
                    "confidence": 0.95,
                    "evidence_id": "evidence-1",
                    "value": "wholesale_colocation",
                }
            ),
            "wholesale_colocation",
        )
        row = _row()
        row["operating_model_observation"] = {
            "confidence": 0.95,
            "evidence_id": "evidence-1",
            "value": "wholesale_colocation",
        }
        index, _coverage = build_index(
            [row],
            master_manifest={
                "generated_at": "2026-07-18T00:00:00Z",
                "master_id": "fixture",
                "row_counts": {"total": 1},
            },
            master_manifest_sha256="a" * 64,
        )
        projected = dict(zip(FIELDS, index["rows"][0], strict=True))
        self.assertEqual(projected["operating_model"], "wholesale_colocation")

    def test_partial_coordinate_fails_closed(self) -> None:
        manifest = {
            "generated_at": "2026-07-18T00:00:00Z",
            "master_id": "fixture",
            "row_counts": {"total": 1},
        }
        with self.assertRaisesRegex(ConstructionMapError, "partial coordinate"):
            build_index(
                [_row(latitude=None, longitude=2)],
                master_manifest=manifest,
                master_manifest_sha256="a" * 64,
            )

    def test_strict_projection_rejects_count_and_missing_id_drift(self) -> None:
        manifest = {
            "generated_at": "2026-07-18T00:00:00Z",
            "master_id": "fixture",
            "row_counts": {"total": 2},
        }
        rows = [
            _row(),
            _row(row_id="row-2", tier="B", latitude=None, longitude=None),
        ]
        expected = {
            "default_visible_rows": 1,
            "default_visible_tiers": list(DEFAULT_VISIBLE_TIERS),
            "mapped_by_tier": {"A": 1, "B": 0, "C": 0},
            "mapped_rows": 1,
            "master_rows": 2,
            "unmapped_rows": 1,
            "unmapped_source_record_ids": ["row-2"],
        }
        build_index(
            rows,
            master_manifest=manifest,
            master_manifest_sha256="a" * 64,
            expected_projection=expected,
        )
        changed = deepcopy(expected)
        changed["unmapped_source_record_ids"] = ["invented-coordinate-target"]
        with self.assertRaisesRegex(ConstructionMapError, "strict definition"):
            build_index(
                rows,
                master_manifest=manifest,
                master_manifest_sha256="a" * 64,
                expected_projection=changed,
            )

    def test_scope_cannot_be_promoted(self) -> None:
        self.assertFalse(MAP_SCOPE["atlas_claims_created"])
        self.assertTrue(MAP_SCOPE["map_rows_are_observations_not_unique_sites"])
        self.assertIsNone(MAP_SCOPE["unique_physical_site_count"])

    def test_public_open_v1_through_v6_bytes_remain_pinned(self) -> None:
        for version, expected in LEGACY_BUNDLE_INVENTORY_SHA256.items():
            release_date = "2026-07-19" if version == "v6" else "2026-07-18"
            bundle = (
                PROJECT_ROOT
                / "construction_maps"
                / f"{release_date}-public-open-{version}"
            )
            self.assertEqual(_bundle_inventory_sha256(bundle), expected)

    def test_bundle_is_deterministic_and_embeds_only_base64_gzip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            master, definition = _master_fixture(root)
            first = root / "first"
            second = root / "second"
            write_construction_map(
                master, first, master_definition_path=definition, validate_master=False
            )
            write_construction_map(
                master, second, master_definition_path=definition, validate_master=False
            )
            for original in sorted(first.iterdir()):
                self.assertEqual(original.read_bytes(), (second / original.name).read_bytes())
            compressed = (first / "construction-map-index.json.gz").read_bytes()
            self.assertEqual(compressed[9], 255)
            decoded = json.loads(gzip.decompress(compressed))
            self.assertEqual(len(decoded["rows"]), 1)
            html = (first / "construction-map.html").read_text(encoding="utf-8")
            self.assertNotIn("Example </script> campus", html)
            encoded = html.split(
                '<script id="construction-map-data" type="application/octet-stream">', 1
            )[1].split("</script>", 1)[0]
            self.assertEqual(base64.b64decode(encoded), compressed)

    def test_freeze_modes_and_cross_python_gzip_header(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            master, definition = _master_fixture(root)
            bundle = root / "frozen"
            write_construction_map(
                master,
                bundle,
                master_definition_path=definition,
                validate_master=False,
                freeze=True,
            )
            self.assertTrue(is_frozen_map(bundle))
            bundle.chmod(0o755)
            for entry in bundle.iterdir():
                entry.chmod(0o644)

        command = (
            "import base64; "
            "from datacenter_atlas.construction_map import _gzip; "
            "print(base64.b64encode(_gzip(b'cross-python-map-v5')).decode())"
        )
        executables = {sys.executable, shutil.which("python3")}
        encoded_outputs = set()
        for executable in sorted(value for value in executables if value):
            completed = subprocess.run(
                [executable, "-c", command],
                cwd=PROJECT_ROOT,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                check=True,
                capture_output=True,
                text=True,
            )
            compressed = base64.b64decode(completed.stdout.strip())
            self.assertEqual(compressed[9], 255)
            encoded_outputs.add(completed.stdout.strip())
        self.assertEqual(len(encoded_outputs), 1)

    def test_static_validator_rejects_tampering_and_extra_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            master, definition = _master_fixture(root)
            bundle = root / "map"
            write_construction_map(
                master, bundle, master_definition_path=definition, validate_master=False
            )
            validate_construction_map(bundle, reproduce=False)
            copied = root / "copied"
            shutil.copytree(bundle, copied)
            (copied / "extra.txt").write_text("unexpected", encoding="utf-8")
            with self.assertRaisesRegex(ConstructionMapError, "closed file set"):
                validate_construction_map(copied, reproduce=False)

            changed = root / "changed"
            shutil.copytree(bundle, changed)
            (changed / "construction-map-index.json.gz").write_bytes(b"changed")
            with self.assertRaisesRegex(ConstructionMapError, "output changed"):
                validate_construction_map(changed, reproduce=False)

    def test_public_open_v3_is_frozen_and_reproduces_from_pinned_master(self) -> None:
        definition_raw = V3_DEFINITION.read_bytes()
        definition = json.loads(definition_raw)
        self.assertEqual(
            definition_raw,
            (json.dumps(definition, indent=2, sort_keys=True) + "\n").encode(),
        )
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "161baf08167ec90831477af7d96532450e36ccb9d338e26b625e226c8d74907d",
        )
        self.assertEqual(
            set(definition),
            {
                "definition_role",
                "expected_projection",
                "format",
                "generated_at",
                "map_id",
                "master",
                "schema_version",
                "scope",
                "template",
            },
        )
        self.assertEqual(
            definition["definition_role"],
            "external_provenance_pin_not_consumed_by_map_validator",
        )
        self.assertEqual(definition["scope"], MAP_SCOPE)
        self.assertEqual(
            definition["master"],
            {
                "definition": {
                    "bytes": 10346,
                    "path": "construction-master-2026-07-18-public-open-v3.json",
                    "sha256": "0b7654bb0b3f37960c47b76efc34d65bf121d0179ac4151c3b08735d236e258b",
                },
                "directory": "../construction_master/2026-07-18-public-open-v3",
                "jsonl": {
                    "bytes": 306997385,
                    "path": "../construction_master/2026-07-18-public-open-v3/construction-master.jsonl",
                    "sha256": "e3b8e5c19c3fd12e0910b49a772da2b8ea207c8183d7c046893ae59cd349a465",
                },
                "manifest": {
                    "bytes": 29705,
                    "path": "../construction_master/2026-07-18-public-open-v3/manifest.json",
                    "sha256": "d945e1dddc6b80d4eda069e109275982869c8a7cef5a7920ce61ad8a1a87e2dd",
                },
                "master_id": "2026-07-18-public-open-v3",
            },
        )
        for key in ("definition", "jsonl", "manifest"):
            checkpoint = definition["master"][key]
            path = (V3_DEFINITION.parent / checkpoint["path"]).resolve()
            raw = path.read_bytes()
            self.assertEqual(len(raw), checkpoint["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), checkpoint["sha256"])
        template = definition["template"]
        template_raw = (V3_DEFINITION.parent / template["path"]).resolve().read_bytes()
        self.assertEqual(len(template_raw), template["bytes"])
        self.assertEqual(hashlib.sha256(template_raw).hexdigest(), template["sha256"])

        manifest = validate_construction_map(
            V3_MAP,
            master_directory=V3_MASTER,
            master_definition_path=V3_MASTER_DEFINITION,
            reproduce=True,
        )
        manifest_raw = (V3_MAP / "manifest.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(manifest_raw).hexdigest(),
            "7313b458d0d506302e50dd1bffc9b227ae40701bf804d8a8fc74cb3fada51232",
        )
        self.assertEqual(
            (V3_MAP / "manifest.sha256").read_text(encoding="ascii"),
            "7313b458d0d506302e50dd1bffc9b227ae40701bf804d8a8fc74cb3fada51232  manifest.json\n",
        )
        self.assertEqual(manifest["map_id"], definition["map_id"])
        self.assertEqual(manifest["scope"], definition["scope"])
        self.assertEqual(manifest["master"]["rows"], 108900)
        self.assertEqual(
            manifest["outputs"]["construction-map-index.json.gz"]["records"],
            108889,
        )

        coverage = json.loads((V3_MAP / "coverage.json").read_text(encoding="utf-8"))
        expected = definition["expected_projection"]
        self.assertEqual(
            coverage["counts"],
            {
                "mapped_observation_rows": expected["mapped_rows"],
                "master_observation_rows": expected["master_rows"],
                "unique_physical_site_count": None,
                "unmapped_observation_rows": expected["unmapped_rows"],
            },
        )
        self.assertEqual(coverage["mapped_counts"]["by_tier"], expected["mapped_by_tier"])
        self.assertEqual(
            sum(
                coverage["mapped_counts"]["by_tier"][tier]
                for tier in expected["default_visible_tiers"]
            ),
            expected["default_visible_rows"],
        )

        compressed = (V3_MAP / "construction-map-index.json.gz").read_bytes()
        index = json.loads(gzip.decompress(compressed))
        tier_column = index["fields"].index("tier")
        self.assertEqual(
            dict(sorted(Counter(row[tier_column] for row in index["rows"]).items())),
            expected["mapped_by_tier"],
        )

        unmapped_source_ids = []
        with (V3_MASTER / "construction-master.jsonl").open(encoding="utf-8") as source:
            for line in source:
                row = json.loads(line)
                entity = row["entity"]
                if entity["latitude"] is None and entity["longitude"] is None:
                    unmapped_source_ids.append(row["source"]["record_id"])
        self.assertEqual(sorted(unmapped_source_ids), expected["unmapped_source_record_ids"])
        self.assertIn(
            "england-planning-data:10000088724",
            expected["unmapped_source_record_ids"],
        )
        self.assertEqual(V3_MAP.stat().st_mode & 0o777, 0o555)
        for path in V3_MAP.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_public_open_v4_is_frozen_and_reproduces_from_pinned_master(self) -> None:
        definition_raw = V4_DEFINITION.read_bytes()
        definition = json.loads(definition_raw)
        self.assertEqual(
            definition_raw,
            (json.dumps(definition, indent=2, sort_keys=True) + "\n").encode(),
        )
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "95b66454fb5d8eb2003ab891dc218e5898b55c84e5752a098d7b2879a048f5ca",
        )
        self.assertEqual(
            set(definition),
            {
                "definition_role",
                "expected_projection",
                "format",
                "generated_at",
                "map_id",
                "master",
                "schema_version",
                "scope",
                "template",
            },
        )
        self.assertEqual(
            definition["definition_role"],
            "external_provenance_pin_not_consumed_by_map_validator",
        )
        self.assertEqual(definition["scope"], MAP_SCOPE)
        self.assertEqual(
            definition["master"],
            {
                "definition": {
                    "bytes": 13408,
                    "path": "construction-master-2026-07-18-public-open-v4.json",
                    "sha256": "7ba4c9706b76457effc9e1e785f035a73acd80cf1e88dc377b026c1c07348856",
                },
                "directory": "../construction_master/2026-07-18-public-open-v4",
                "jsonl": {
                    "bytes": 307455717,
                    "path": "../construction_master/2026-07-18-public-open-v4/construction-master.jsonl",
                    "sha256": "75dc9e7e5b5995343b9d17472ed6e4b4e6e4ca606bc6c0f956f892118b437f3a",
                },
                "manifest": {
                    "bytes": 37128,
                    "path": "../construction_master/2026-07-18-public-open-v4/manifest.json",
                    "sha256": "1e41d10218c9c99f3343f2ad6ad78b9eda89e2584ffe1a671a6670d41168533a",
                },
                "master_id": "2026-07-18-public-open-v4",
            },
        )
        for key in ("definition", "jsonl", "manifest"):
            checkpoint = definition["master"][key]
            path = (V4_DEFINITION.parent / checkpoint["path"]).resolve()
            raw = path.read_bytes()
            self.assertEqual(len(raw), checkpoint["bytes"])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), checkpoint["sha256"])
        template = definition["template"]
        template_raw = (V4_DEFINITION.parent / template["path"]).resolve().read_bytes()
        self.assertEqual(len(template_raw), template["bytes"])
        self.assertEqual(hashlib.sha256(template_raw).hexdigest(), template["sha256"])

        manifest = validate_construction_map(
            V4_MAP,
            master_directory=V4_MASTER,
            master_definition_path=V4_MASTER_DEFINITION,
            reproduce=True,
        )
        manifest_raw = (V4_MAP / "manifest.json").read_bytes()
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        self.assertEqual(
            manifest_sha,
            "b466c2fb8dce3ee6ad7f965e44aa730c417472ec5b2dca99df7dc68823c707fe",
        )
        self.assertEqual(
            (V4_MAP / "manifest.sha256").read_text(encoding="ascii"),
            f"{manifest_sha}  manifest.json\n",
        )
        self.assertEqual(manifest["map_id"], definition["map_id"])
        self.assertEqual(manifest["scope"], definition["scope"])
        self.assertEqual(manifest["master"]["rows"], 108944)
        self.assertEqual(
            manifest["outputs"]["construction-map-index.json.gz"]["records"],
            108929,
        )

        coverage = json.loads((V4_MAP / "coverage.json").read_text(encoding="utf-8"))
        expected = definition["expected_projection"]
        self.assertEqual(
            coverage["counts"],
            {
                "mapped_observation_rows": expected["mapped_rows"],
                "master_observation_rows": expected["master_rows"],
                "unique_physical_site_count": None,
                "unmapped_observation_rows": expected["unmapped_rows"],
            },
        )
        self.assertEqual(coverage["mapped_counts"]["by_tier"], expected["mapped_by_tier"])
        self.assertEqual(
            sum(
                coverage["mapped_counts"]["by_tier"][tier]
                for tier in expected["default_visible_tiers"]
            ),
            expected["default_visible_rows"],
        )

        compressed = (V4_MAP / "construction-map-index.json.gz").read_bytes()
        index = json.loads(gzip.decompress(compressed))
        tier_column = index["fields"].index("tier")
        self.assertEqual(
            dict(sorted(Counter(row[tier_column] for row in index["rows"]).items())),
            expected["mapped_by_tier"],
        )

        unmapped_source_ids = []
        with (V4_MASTER / "construction-master.jsonl").open(encoding="utf-8") as source:
            for line in source:
                row = json.loads(line)
                entity = row["entity"]
                if entity["latitude"] is None and entity["longitude"] is None:
                    unmapped_source_ids.append(row["source"]["record_id"])
        self.assertEqual(sorted(unmapped_source_ids), expected["unmapped_source_record_ids"])
        self.assertIn(
            "netherlands-koop:prb-2026-11305",
            expected["unmapped_source_record_ids"],
        )
        self.assertEqual(V4_MAP.stat().st_mode & 0o777, 0o555)
        for path in V4_MAP.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)

    def test_public_open_v5_strict_contract_reproduces_and_keeps_france_unmapped(
        self,
    ) -> None:
        definition_raw = V5_DEFINITION.read_bytes()
        definition = json.loads(definition_raw)
        self.assertEqual(
            definition_raw,
            (json.dumps(definition, indent=2, sort_keys=True) + "\n").encode(),
        )
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "cc21bbc7f2ee0bd9e043dd8fde8c477632e9d6f301e9da77cb43500e8781da07",
        )
        self.assertEqual(definition["definition_role"], STRICT_DEFINITION_ROLE)
        expected = definition["expected_projection"]
        self.assertEqual(
            expected,
            {
                "default_visible_rows": 6447,
                "default_visible_tiers": ["A", "B"],
                "mapped_by_tier": {"A": 167, "B": 6280, "C": 102494},
                "mapped_rows": 108941,
                "master_rows": 108960,
                "unmapped_rows": 19,
                "unmapped_source_record_ids": [
                    "ed36ec2d-e010-52e8-8d72-a0424647a1d1",
                    "england-planning-data:10000088724",
                    "fr-igedd-ae-2021-104",
                    "fr-igedd-ae-2024-08",
                    "fr-igedd-ae-2025-058",
                    "fr-igedd-ae-2026-33",
                    "netherlands-koop:prb-2026-11305",
                    "new-zealand-fast-track:auckland-surf-park-2022-116",
                    "new-zealand-fast-track:auckland-surf-park-stage-2",
                    "new-zealand-fast-track:datagrid-fta104",
                    "sec-edgar-edgm-caceres",
                    "sec-edgar-edgm-cordoba",
                    "sec-edgar-edgm-malpica-mora",
                    "sec-edgar-edgm-palma-unresolved",
                    "sec-edgar-edgm-tocumen",
                    "sec-edgar-edgm-tomelloso",
                    "sec-edgar-edgm-torrecampo",
                    "sec-edgar-edgm-vianos",
                    "sec-edgar-edgm-villasequilla",
                ],
            },
        )

        manifest = validate_construction_map(
            V5_MAP,
            master_directory=V5_MASTER,
            master_definition_path=V5_MASTER_DEFINITION,
            map_definition_path=V5_DEFINITION,
            reproduce=True,
        )
        manifest_raw = (V5_MAP / "manifest.json").read_bytes()
        self.assertEqual(
            hashlib.sha256(manifest_raw).hexdigest(),
            "f1820bced7d1641ac9cb8821a70e0ba148c2b390980654accbef852fa8798030",
        )
        self.assertEqual(manifest["map_id"], definition["map_id"])
        self.assertEqual(manifest["master"]["rows"], expected["master_rows"])
        self.assertEqual(
            manifest["outputs"]["construction-map-index.json.gz"]["records"],
            expected["mapped_rows"],
        )

        coverage = json.loads((V5_MAP / "coverage.json").read_text())
        self.assertEqual(
            coverage["counts"],
            {
                "mapped_observation_rows": expected["mapped_rows"],
                "master_observation_rows": expected["master_rows"],
                "unique_physical_site_count": None,
                "unmapped_observation_rows": expected["unmapped_rows"],
            },
        )
        self.assertEqual(
            coverage["mapped_counts"]["by_tier"], expected["mapped_by_tier"]
        )

        france_ids = {
            "fr-igedd-ae-2021-104",
            "fr-igedd-ae-2024-08",
            "fr-igedd-ae-2025-058",
            "fr-igedd-ae-2026-33",
        }
        unmapped_ids = []
        france_master_rows = {}
        with (V5_MASTER / "construction-master.jsonl").open() as source:
            for line in source:
                row = json.loads(line)
                entity = row["entity"]
                source_record_id = row["source"]["record_id"]
                if entity["latitude"] is None and entity["longitude"] is None:
                    unmapped_ids.append(source_record_id)
                if source_record_id in france_ids:
                    france_master_rows[source_record_id] = entity
        self.assertEqual(sorted(unmapped_ids), expected["unmapped_source_record_ids"])
        self.assertEqual(set(france_master_rows), france_ids)
        for entity in france_master_rows.values():
            self.assertIsNone(entity["latitude"])
            self.assertIsNone(entity["longitude"])

        compressed = (V5_MAP / "construction-map-index.json.gz").read_bytes()
        self.assertEqual(compressed[9], 255)
        index = json.loads(gzip.decompress(compressed))
        tier_column = index["fields"].index("tier")
        source_record_column = index["fields"].index("source_record_id")
        self.assertEqual(
            dict(Counter(row[tier_column] for row in index["rows"])),
            expected["mapped_by_tier"],
        )
        self.assertTrue(
            france_ids.isdisjoint(
                row[source_record_column] for row in index["rows"]
            )
        )
        self.assertTrue(is_frozen_map(V5_MAP))

    def test_public_open_v6_strict_contract_reproduces_exact_projection(self) -> None:
        definition_raw = V6_DEFINITION.read_bytes()
        definition = json.loads(definition_raw)
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "7bcd9e891621b39a780a883e24e6c64be22e13c47ad05357bb1b715dcf96e0be",
        )
        expected = definition["expected_projection"]
        self.assertEqual(
            expected,
            {
                "default_visible_rows": 6451,
                "default_visible_tiers": ["A", "B"],
                "mapped_by_tier": {"A": 171, "B": 6280, "C": 102494},
                "mapped_rows": 108945,
                "master_rows": 108964,
                "unmapped_rows": 19,
                "unmapped_source_record_ids": [
                    "ed36ec2d-e010-52e8-8d72-a0424647a1d1",
                    "england-planning-data:10000088724",
                    "fr-igedd-ae-2021-104",
                    "fr-igedd-ae-2024-08",
                    "fr-igedd-ae-2025-058",
                    "fr-igedd-ae-2026-33",
                    "netherlands-koop:prb-2026-11305",
                    "new-zealand-fast-track:auckland-surf-park-2022-116",
                    "new-zealand-fast-track:auckland-surf-park-stage-2",
                    "new-zealand-fast-track:datagrid-fta104",
                    "sec-edgar-edgm-caceres",
                    "sec-edgar-edgm-cordoba",
                    "sec-edgar-edgm-malpica-mora",
                    "sec-edgar-edgm-palma-unresolved",
                    "sec-edgar-edgm-tocumen",
                    "sec-edgar-edgm-tomelloso",
                    "sec-edgar-edgm-torrecampo",
                    "sec-edgar-edgm-vianos",
                    "sec-edgar-edgm-villasequilla",
                ],
            },
        )
        manifest = validate_construction_map(
            V6_MAP,
            master_directory=V6_MASTER,
            master_definition_path=V6_MASTER_DEFINITION,
            map_definition_path=V6_DEFINITION,
            reproduce=True,
        )
        self.assertEqual(
            hashlib.sha256((V6_MAP / "manifest.json").read_bytes()).hexdigest(),
            "14663b26824244fbf665a668fd3af7a59d07759ce68d04a78b29589d7350c3c4",
        )
        self.assertEqual(manifest["master"]["rows"], 108964)
        self.assertEqual(
            manifest["outputs"]["construction-map-index.json.gz"]["records"],
            108945,
        )
        coverage = json.loads((V6_MAP / "coverage.json").read_text())
        self.assertEqual(coverage["mapped_counts"]["by_tier"], expected["mapped_by_tier"])
        self.assertTrue(is_frozen_map(V6_MAP))

    def test_v6_map_contains_all_four_meta_projects_without_metrics(self) -> None:
        index = json.loads(
            gzip.decompress((V6_MAP / "construction-map-index.json.gz").read_bytes())
        )
        fields = index["fields"]
        by_name = [dict(zip(fields, row, strict=True)) for row in index["rows"]]
        expected_names = {
            "Meta El Paso Current Development",
            "Meta Lebanon Current Development",
            "Meta Richland Parish Current Development",
            "Meta Tulsa Current Development",
        }
        meta_rows = [
            row
            for row in by_name
            if row["source_artifact_id"] == "epoch-official-open-seed-v2"
            and row["name"] in expected_names
        ]
        self.assertEqual(len(meta_rows), 4)
        self.assertEqual({row["name"] for row in meta_rows}, expected_names)
        for row in meta_rows:
            self.assertEqual(row["tier"], "A")
            self.assertEqual(row["entity_kind"], "project")
            self.assertEqual(row["normalized_status"], "under_construction")
            self.assertEqual(row["reported_status_date"], "2026-04-28")
            self.assertEqual(row["capacity_observations"], [])
            self.assertEqual(row["annual_energy_observations"], [])
            self.assertEqual(row["pue_observations"], [])
            self.assertEqual(row["untyped_capacity_statements"], [])
            self.assertEqual(row["workloads"], ["mixed"])

    def test_public_open_v7_strict_contract_reproduces_exact_projection(self) -> None:
        definition_raw = V7_DEFINITION.read_bytes()
        definition = json.loads(definition_raw)
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "042b4b4a1a8390ddace17beaeb398d4ca7629da96abc36cddc56c1704940d884",
        )
        expected = definition["expected_projection"]
        self.assertEqual(expected["default_visible_rows"], 6457)
        self.assertEqual(
            expected["mapped_by_tier"], {"A": 177, "B": 6280, "C": 102494}
        )
        self.assertEqual(expected["mapped_rows"], 108951)
        self.assertEqual(expected["master_rows"], 108970)
        self.assertEqual(expected["unmapped_rows"], 19)
        self.assertEqual(
            expected["unmapped_source_record_ids"],
            json.loads(V6_DEFINITION.read_text())["expected_projection"][
                "unmapped_source_record_ids"
            ],
        )
        manifest = validate_construction_map(
            V7_MAP,
            master_directory=V7_MASTER,
            master_definition_path=V7_MASTER_DEFINITION,
            map_definition_path=V7_DEFINITION,
            reproduce=True,
        )
        self.assertEqual(
            hashlib.sha256((V7_MAP / "manifest.json").read_bytes()).hexdigest(),
            "7cbac51f9a507090dc06f7110defde2e54ef4bc8f5c2b12c7d095e91a1545870",
        )
        self.assertEqual(manifest["master"]["rows"], 108970)
        self.assertEqual(
            manifest["outputs"]["construction-map-index.json.gz"]["records"],
            108951,
        )
        coverage = json.loads((V7_MAP / "coverage.json").read_text())
        self.assertEqual(coverage["mapped_counts"]["by_tier"], expected["mapped_by_tier"])
        self.assertTrue(is_frozen_map(V7_MAP))

    def test_v7_map_contains_google_delta_and_one_meta_copy_without_metrics(self) -> None:
        index = json.loads(
            gzip.decompress((V7_MAP / "construction-map-index.json.gz").read_bytes())
        )
        fields = index["fields"]
        rows = [dict(zip(fields, row, strict=True)) for row in index["rows"]]
        google_names = {
            "Google Horndal Data Center Current Development",
            "Google Meitner Energy Center Data Center Current Development",
            "Google Muskogee Data Center Current Development",
            "Google Stillwater Data Center Current Development",
            "Google Visakhapatnam AI Hub Data Center Current Development",
            "Google Wilbarger County Data Center Current Development",
        }
        meta_names = {
            "Meta El Paso Current Development",
            "Meta Lebanon Current Development",
            "Meta Richland Parish Current Development",
            "Meta Tulsa Current Development",
        }
        selected = [
            row
            for row in rows
            if row["source_artifact_id"] == "epoch-official-open-seed-v4"
            and row["name"] in google_names | meta_names
        ]
        self.assertEqual(len(selected), 10)
        self.assertEqual({row["name"] for row in selected}, google_names | meta_names)
        for row in selected:
            self.assertEqual(row["tier"], "A")
            self.assertEqual(row["entity_kind"], "project")
            self.assertEqual(row["normalized_status"], "under_construction")
            self.assertEqual(row["capacity_observations"], [])
            self.assertEqual(row["annual_energy_observations"], [])
            self.assertEqual(row["pue_observations"], [])
            self.assertEqual(row["untyped_capacity_statements"], [])
            self.assertIsNone(row["operating_model"])

    def test_public_open_v8_strict_contract_reproduces_exact_projection(self) -> None:
        self.assertEqual(
            _bundle_inventory_sha256(V7_MAP),
            V7_MAP_BUNDLE_INVENTORY_SHA256,
        )
        definition_raw = V8_DEFINITION.read_bytes()
        definition = json.loads(definition_raw)
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "b76fe3501fe03bb8950268b661cee6cc68c240120ec3324b69fd0ff458657bba",
        )
        expected = definition["expected_projection"]
        self.assertEqual(expected["default_visible_rows"], 6459)
        self.assertEqual(
            expected["mapped_by_tier"], {"A": 179, "B": 6280, "C": 102494}
        )
        self.assertEqual(expected["mapped_rows"], 108953)
        self.assertEqual(expected["master_rows"], 108972)
        self.assertEqual(expected["unmapped_rows"], 19)
        self.assertEqual(
            expected["unmapped_source_record_ids"],
            json.loads(V7_DEFINITION.read_text())["expected_projection"][
                "unmapped_source_record_ids"
            ],
        )
        manifest = validate_construction_map(
            V8_MAP,
            master_directory=V8_MASTER,
            master_definition_path=V8_MASTER_DEFINITION,
            map_definition_path=V8_DEFINITION,
            reproduce=True,
        )
        self.assertEqual(
            hashlib.sha256((V8_MAP / "manifest.json").read_bytes()).hexdigest(),
            "6413fd6471c7476d2ae88a2eef862400f5c0bb07215f157fc312058161eb82ef",
        )
        self.assertEqual(manifest["master"]["rows"], 108972)
        self.assertEqual(
            manifest["outputs"]["construction-map-index.json.gz"]["records"],
            108953,
        )
        coverage = json.loads((V8_MAP / "coverage.json").read_text())
        self.assertEqual(coverage["mapped_counts"]["by_tier"], expected["mapped_by_tier"])
        self.assertTrue(is_frozen_map(V8_MAP))
        self.assertTrue(all(not entry.is_symlink() for entry in V8_MAP.iterdir()))

    def test_v8_map_adds_only_the_two_source_scoped_microsoft_projects(self) -> None:
        index = json.loads(
            gzip.decompress((V8_MAP / "construction-map-index.json.gz").read_bytes())
        )
        fields = index["fields"]
        rows = [dict(zip(fields, row, strict=True)) for row in index["rows"]]
        microsoft_rows = [
            row
            for row in rows
            if row["source_artifact_id"] == "epoch-official-open-seed-v5"
            and row["source_publisher"] == "Microsoft"
        ]
        self.assertEqual(len(microsoft_rows), 2)
        self.assertEqual(
            {row["name"] for row in microsoft_rows},
            {
                "Microsoft Mount Pleasant Second Datacenter Facility",
                "Microsoft Pecos Datacenter Campus Development",
            },
        )
        by_name = {row["name"]: row for row in microsoft_rows}
        self.assertEqual(
            by_name["Microsoft Mount Pleasant Second Datacenter Facility"][
                "normalized_status"
            ],
            "under_construction",
        )
        self.assertEqual(
            by_name["Microsoft Pecos Datacenter Campus Development"][
                "normalized_status"
            ],
            "announced",
        )
        self.assertEqual(
            by_name["Microsoft Mount Pleasant Second Datacenter Facility"][
                "workloads"
            ],
            [],
        )
        self.assertEqual(
            by_name["Microsoft Pecos Datacenter Campus Development"]["workloads"],
            ["mixed"],
        )
        for row in microsoft_rows:
            self.assertEqual(row["tier"], "A")
            self.assertEqual(row["entity_kind"], "project")
            self.assertEqual(row["capacity_observations"], [])
            self.assertEqual(row["annual_energy_observations"], [])
            self.assertEqual(row["pue_observations"], [])
            self.assertEqual(row["untyped_capacity_statements"], [])
            self.assertIsNone(row["operating_model"])
            self.assertFalse(row["construction_verified"])
            self.assertEqual(row["resolution_advisory_count"], 0)

    def test_public_open_v9_strict_contract_reproduces_exact_projection(self) -> None:
        self.assertEqual(
            _bundle_inventory_sha256(V8_MAP),
            V8_MAP_BUNDLE_INVENTORY_SHA256,
        )
        definition_raw = V9_DEFINITION.read_bytes()
        definition = json.loads(definition_raw)
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "e3d57ce10175b6186e4b54f09a8ff8ef3f3022683eea2bb2fb91940642132a07",
        )
        expected = definition["expected_projection"]
        self.assertEqual(expected["default_visible_rows"], 6472)
        self.assertEqual(
            expected["mapped_by_tier"], {"A": 192, "B": 6280, "C": 102494}
        )
        self.assertEqual(expected["mapped_rows"], 108966)
        self.assertEqual(expected["master_rows"], 108985)
        self.assertEqual(expected["unmapped_rows"], 19)
        self.assertEqual(
            expected["unmapped_source_record_ids"],
            json.loads(V8_DEFINITION.read_text())["expected_projection"][
                "unmapped_source_record_ids"
            ],
        )
        manifest = validate_construction_map(
            V9_MAP,
            master_directory=V9_MASTER,
            master_definition_path=V9_MASTER_DEFINITION,
            map_definition_path=V9_DEFINITION,
            reproduce=True,
        )
        self.assertEqual(
            hashlib.sha256((V9_MAP / "manifest.json").read_bytes()).hexdigest(),
            "c0c79dc5c431a73cbb6853720e5fa4dec6417fb49adf3dc1e4a3aa3c5101d53a",
        )
        self.assertEqual(
            _bundle_inventory_sha256(V9_MAP),
            V9_MAP_BUNDLE_INVENTORY_SHA256,
        )
        self.assertEqual(manifest["master"]["rows"], 108985)
        self.assertEqual(
            manifest["outputs"]["construction-map-index.json.gz"]["records"],
            108966,
        )
        coverage = json.loads((V9_MAP / "coverage.json").read_text())
        self.assertEqual(coverage["mapped_counts"]["by_tier"], expected["mapped_by_tier"])
        self.assertTrue(is_frozen_map(V9_MAP))
        self.assertTrue(all(not entry.is_symlink() for entry in V9_MAP.iterdir()))

    def test_v9_map_preserves_capacity_stages_and_coreweave_operating_model(self) -> None:
        previous_index = json.loads(
            gzip.decompress((V8_MAP / "construction-map-index.json.gz").read_bytes())
        )
        current_index = json.loads(
            gzip.decompress((V9_MAP / "construction-map-index.json.gz").read_bytes())
        )
        previous_rows = [
            dict(zip(previous_index["fields"], row, strict=True))
            for row in previous_index["rows"]
            if row[previous_index["fields"].index("source_artifact_id")]
            == "epoch-official-open-seed-v5"
        ]
        current_rows = [
            dict(zip(current_index["fields"], row, strict=True))
            for row in current_index["rows"]
            if row[current_index["fields"].index("source_artifact_id")]
            == "epoch-official-open-seed-v9"
        ]
        previous_ids = {row["source_record_id"] for row in previous_rows}
        current_by_id = {row["source_record_id"]: row for row in current_rows}
        self.assertEqual(set(current_by_id) - previous_ids, V9_ADDITION_IDS)
        additions = [current_by_id[record_id] for record_id in V9_ADDITION_IDS]
        for row in additions:
            self.assertEqual(row["tier"], "A")
            self.assertEqual(row["entity_kind"], "project")
            self.assertEqual(row["normalized_status"], "under_construction")
            self.assertTrue(row["construction_source_supported"])
            self.assertFalse(row["construction_verified"])
            self.assertEqual(row["annual_energy_observations"], [])
            self.assertEqual(row["pue_observations"], [])
            self.assertEqual(row["untyped_capacity_statements"], [])
            self.assertIsNone(row["operating_model"])
        capacity = [
            observation
            for row in additions
            for observation in row["capacity_observations"]
        ]
        self.assertEqual(len(capacity), 5)
        self.assertTrue(
            all(
                observation[0] == "critical_it_mw"
                and observation[1] == observation[2] == observation[3]
                and observation[4] == "MW"
                and observation[6] is None
                and observation[7] == "reported"
                and observation[8] == 0.99
                for observation in capacity
            )
        )
        by_stage = Counter()
        for observation in capacity:
            by_stage[observation[5]] += observation[1]
        self.assertEqual(by_stage, Counter({"contracted": 600.0, "planned": 300.0}))
        self.assertNotIn(576.0, [observation[1] for observation in capacity])
        self.assertEqual(
            Counter(workload for row in additions for workload in row["workloads"]),
            Counter({"mixed": 8, "ai_specialized_unspecified": 2}),
        )
        operating_rows = [
            dict(zip(current_index["fields"], row, strict=True))
            for row in current_index["rows"]
            if row[current_index["fields"].index("operating_model")] is not None
        ]
        self.assertEqual(len(operating_rows), 1)
        self.assertEqual(
            (
                operating_rows[0]["source_record_id"],
                operating_rows[0]["operating_model"],
            ),
            (
                "b99b03ae-8105-517c-a9ac-7c6d4d4fecbd",
                "wholesale_colocation",
            ),
        )

    def test_frozen_v10_map_reproduces_exact_projection_offline(self) -> None:
        definition_raw = V10_DEFINITION.read_bytes()
        definition = json.loads(definition_raw)
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "e713cc3c18823c26cd3759fb5a1522b0c0d25771bacaf96cd0472af5fd960383",
        )
        expected = definition["expected_projection"]
        self.assertEqual(expected["default_visible_rows"], 6478)
        self.assertEqual(
            expected["mapped_by_tier"], {"A": 198, "B": 6280, "C": 102494}
        )
        self.assertEqual(expected["mapped_rows"], 108972)
        self.assertEqual(expected["master_rows"], 109017)
        self.assertEqual(expected["unmapped_rows"], 45)
        previous_unmapped = set(
            json.loads(V9_DEFINITION.read_text())["expected_projection"][
                "unmapped_source_record_ids"
            ]
        )
        current_unmapped = set(expected["unmapped_source_record_ids"])
        self.assertEqual(current_unmapped & previous_unmapped, previous_unmapped)
        self.assertEqual(len(current_unmapped - previous_unmapped), 26)

        manifest = validate_construction_map(
            V10_MAP,
            master_directory=V10_MASTER,
            master_definition_path=V10_MASTER_DEFINITION,
            map_definition_path=V10_DEFINITION,
            reproduce=True,
        )
        self.assertEqual(
            hashlib.sha256((V10_MAP / "manifest.json").read_bytes()).hexdigest(),
            "5b57a6655e11c424b79bf820673c2e55d9cd2eb4687ed1d1c9bca163421e556f",
        )
        self.assertEqual(
            _bundle_inventory_sha256(V10_MAP),
            V10_MAP_BUNDLE_INVENTORY_SHA256,
        )
        self.assertEqual(manifest["master"]["rows"], 109017)
        self.assertEqual(
            manifest["outputs"]["construction-map-index.json.gz"]["records"],
            108972,
        )
        coverage = json.loads((V10_MAP / "coverage.json").read_text())
        self.assertEqual(coverage["mapped_counts"]["by_tier"], expected["mapped_by_tier"])
        self.assertTrue(is_frozen_map(V10_MAP))
        self.assertTrue(all(not entry.is_symlink() for entry in V10_MAP.iterdir()))

    def test_v10_map_adds_only_six_geocoded_metric_free_seed_rows(self) -> None:
        previous_index = json.loads(
            gzip.decompress((V9_MAP / "construction-map-index.json.gz").read_bytes())
        )
        current_index = json.loads(
            gzip.decompress((V10_MAP / "construction-map-index.json.gz").read_bytes())
        )
        previous = {
            row["source_record_id"]: row
            for row in (
                dict(zip(previous_index["fields"], values, strict=True))
                for values in previous_index["rows"]
            )
            if row["source_artifact_id"] == "epoch-official-open-seed-v9"
        }
        current = {
            row["source_record_id"]: row
            for row in (
                dict(zip(current_index["fields"], values, strict=True))
                for values in current_index["rows"]
            )
            if row["source_artifact_id"] == "epoch-official-open-seed-v13"
        }
        addition_ids = set(current) - set(previous)
        self.assertEqual(
            addition_ids,
            {
                "5dfce968-5eac-54c5-a918-38241575dade",
                "64289119-458d-5fc9-bf51-5af6097220eb",
                "8d6cdc86-b9ea-5053-a3a8-9f41a527fe59",
                "b128f3c3-7a64-544d-90a2-7ffd0a04004d",
                "c1af62b5-b9a2-5c15-a8a4-717e1a65ac05",
                "e0495b75-1484-512a-a78a-d665e645423f",
            },
        )
        self.assertEqual(set(previous) - set(current), set())
        ignored = {"row_id", "source_artifact_id", "source_release_id"}
        for record_id in sorted(previous):
            self.assertEqual(
                {key: value for key, value in current[record_id].items() if key not in ignored},
                {key: value for key, value in previous[record_id].items() if key not in ignored},
            )
        additions = [current[record_id] for record_id in sorted(addition_ids)]
        self.assertEqual(
            Counter(row["normalized_status"] for row in additions),
            Counter({"under_construction": 4, "permitted": 2}),
        )
        for row in additions:
            self.assertEqual(row["tier"], "A")
            self.assertEqual(row["entity_kind"], "project")
            self.assertTrue(row["construction_source_supported"])
            self.assertFalse(row["construction_verified"])
            self.assertEqual(row["capacity_observations"], [])
            self.assertEqual(row["annual_energy_observations"], [])
            self.assertEqual(row["pue_observations"], [])
            self.assertEqual(row["untyped_capacity_statements"], [])
            self.assertEqual(row["workloads"], [])
            self.assertIsNone(row["operating_model"])

    def test_frozen_v11_map_reproduces_exact_projection_offline(self) -> None:
        definition_raw = V11_DEFINITION.read_bytes()
        definition = json.loads(definition_raw)
        self.assertEqual(
            hashlib.sha256(definition_raw).hexdigest(),
            "2af41d8d846ea56fbf68a0489e708973ea087351349fb3adc386cc3e3c268986",
        )
        expected = definition["expected_projection"]
        self.assertEqual(expected["default_visible_rows"], 6478)
        self.assertEqual(
            expected["mapped_by_tier"], {"A": 198, "B": 6280, "C": 102494}
        )
        self.assertEqual(expected["mapped_rows"], 108972)
        self.assertEqual(expected["master_rows"], 109063)
        self.assertEqual(expected["unmapped_rows"], 91)

        manifest = validate_construction_map(
            V11_MAP,
            master_directory=V11_MASTER,
            master_definition_path=V11_MASTER_DEFINITION,
            map_definition_path=V11_DEFINITION,
            reproduce=True,
        )
        self.assertEqual(
            hashlib.sha256((V11_MAP / "manifest.json").read_bytes()).hexdigest(),
            "e9aa6e9778edba365572eb92bc87b0612e6daf1f02387eac96046c935ce2c56c",
        )
        self.assertEqual(
            _bundle_inventory_sha256(V11_MAP),
            V11_MAP_BUNDLE_INVENTORY_SHA256,
        )
        self.assertEqual(manifest["master"]["rows"], 109063)
        self.assertEqual(
            manifest["outputs"]["construction-map-index.json.gz"]["records"],
            108972,
        )
        coverage = json.loads((V11_MAP / "coverage.json").read_text())
        self.assertEqual(coverage["mapped_counts"]["by_tier"], expected["mapped_by_tier"])
        self.assertEqual(V11_MAP.stat().st_mode & 0o777, 0o555)
        self.assertTrue(
            all(
                entry.stat().st_mode & 0o777 == 0o444 and not entry.is_symlink()
                for entry in V11_MAP.iterdir()
            )
        )
        self.assertTrue(is_frozen_map(V11_MAP))

    def test_v11_map_keeps_all_v20_additions_explicitly_unmapped(self) -> None:
        previous_definition = json.loads(V10_DEFINITION.read_text())
        current_definition = json.loads(V11_DEFINITION.read_text())
        previous_unmapped = set(
            previous_definition["expected_projection"]["unmapped_source_record_ids"]
        )
        current_unmapped = set(
            current_definition["expected_projection"]["unmapped_source_record_ids"]
        )

        def master_release_ids(master: Path, artifact_id: str) -> set[str]:
            result = set()
            with (master / "construction-master.jsonl").open() as source:
                for raw_line in source:
                    row = json.loads(raw_line)
                    if row["source"]["artifact_id"] == artifact_id:
                        result.add(row["source"]["record_id"])
                    elif result:
                        break
            return result

        previous_master_ids = master_release_ids(
            V10_MASTER, "epoch-official-open-seed-v13"
        )
        current_master_ids = master_release_ids(
            V11_MASTER, "epoch-official-open-seed-v20"
        )
        additions = current_master_ids - previous_master_ids
        self.assertEqual(len(additions), 46)
        self.assertEqual(previous_master_ids - current_master_ids, set())
        self.assertEqual(current_unmapped - previous_unmapped, additions)
        self.assertEqual(previous_unmapped - current_unmapped, set())

        previous_index = json.loads(
            gzip.decompress((V10_MAP / "construction-map-index.json.gz").read_bytes())
        )
        current_index = json.loads(
            gzip.decompress((V11_MAP / "construction-map-index.json.gz").read_bytes())
        )
        previous_rows = {
            row["source_record_id"]: row
            for row in (
                dict(zip(previous_index["fields"], values, strict=True))
                for values in previous_index["rows"]
            )
            if row["source_artifact_id"] == "epoch-official-open-seed-v13"
        }
        current_rows = {
            row["source_record_id"]: row
            for row in (
                dict(zip(current_index["fields"], values, strict=True))
                for values in current_index["rows"]
            )
            if row["source_artifact_id"] == "epoch-official-open-seed-v20"
        }
        self.assertEqual(set(current_rows), set(previous_rows))
        self.assertEqual(set(current_rows) & additions, set())
        ignored = {"row_id", "source_artifact_id", "source_release_id"}
        for record_id in sorted(previous_rows):
            self.assertEqual(
                {
                    key: value
                    for key, value in current_rows[record_id].items()
                    if key not in ignored
                },
                {
                    key: value
                    for key, value in previous_rows[record_id].items()
                    if key not in ignored
                },
            )

    def test_v11_map_definition_guardrails_fail_closed(self) -> None:
        document = json.loads(V11_DEFINITION.read_text())
        changes = []
        changed = deepcopy(document)
        changed["expected_projection"]["mapped_rows"] -= 1
        changes.append((changed, "map definition projection arithmetic differs"))
        changed = deepcopy(document)
        changed["master"]["manifest"]["sha256"] = "0" * 64
        changes.append((changed, "master manifest checkpoint differs"))
        changed = deepcopy(document)
        changed["map_id"] = "changed-map-id"
        changes.append((changed, "map definition master identity changed"))

        for index, (changed, message) in enumerate(changes):
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=V11_DEFINITION.parent,
                prefix=f"changed-v11-map-{index}-",
                suffix=".json",
            ) as temporary:
                temporary.write(
                    json.dumps(changed, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                )
                temporary.flush()
                with self.assertRaisesRegex(ConstructionMapError, message):
                    validate_map_definition(
                        temporary.name,
                        master_directory=V11_MASTER,
                        master_definition_path=V11_MASTER_DEFINITION,
                    )


if __name__ == "__main__":
    unittest.main()
