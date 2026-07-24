from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import socket
import stat
import tempfile
import unittest
from collections import Counter
from unittest.mock import patch

from datacenter_atlas.coverage_audit import (
    AUDIT_FILENAME,
    COVERAGE_CSV_FILENAME,
    GAP_REGISTRY_FILENAME,
    CoverageAuditError,
    build_coverage_audit,
    validate_coverage_audit,
    write_coverage_audit,
)
from datacenter_atlas.federated_release import write_federated_release_index


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_COVERAGE_V5_DEFINITION = (
    ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v5.json"
)
PUBLIC_COVERAGE_V5 = ROOT / "audits" / "2026-07-19-public-open-coverage-v5"
PUBLIC_COVERAGE_V5_MANIFEST_SHA256 = (
    "60ed5943460b2603cc2e54461807cb49f9ab142083a509a680be95126256ffb3"
)
PUBLIC_COVERAGE_V6_DEFINITION = (
    ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v6.json"
)
PUBLIC_COVERAGE_V6 = ROOT / "audits" / "2026-07-19-public-open-coverage-v6"
PUBLIC_COVERAGE_V6_MANIFEST_SHA256 = (
    "2d3e47208fbc338b78ab74383bccd30d71467b67691c30f6701e4b32124b9d56"
)
PUBLIC_COVERAGE_V7_DEFINITION = (
    ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v7.json"
)
PUBLIC_COVERAGE_V7 = ROOT / "audits" / "2026-07-19-public-open-coverage-v7"
PUBLIC_COVERAGE_V7_MANIFEST_SHA256 = (
    "4754f6a95dfc05d63739c3bed137a06649ca827d5a564e61cda38f2a9e6a0074"
)
PUBLIC_COVERAGE_V8_DEFINITION = (
    ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v8.json"
)
PUBLIC_COVERAGE_V8 = ROOT / "audits" / "2026-07-19-public-open-coverage-v8"
PUBLIC_COVERAGE_V8_MANIFEST_SHA256 = (
    "193672219b641b5c8cf21092e563bbd1719fc4ee7c72b51007a3960f1b1ea853"
)
PUBLIC_COVERAGE_V9_DEFINITION = (
    ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v9.json"
)
PUBLIC_COVERAGE_V9_DEFINITION_SHA256 = (
    "459f49d97e8cb884dc5c33c6dc15852c9fbcdf0769c71739b155367923c03997"
)
PUBLIC_COVERAGE_V9 = ROOT / "audits" / "2026-07-19-public-open-coverage-v9"
PUBLIC_COVERAGE_V9_MANIFEST_SHA256 = (
    "657216c910e300314f691e1e726a188c24095bd7b4ec000a97d2a4db7e4ff247"
)
PUBLIC_FEDERATION_V8_MANIFEST_SHA256 = (
    "0db9b8d8ee48c63eb9d95054af42dccc38133be417da5d51cc41b220d0d73f48"
)
PUBLIC_FEDERATION_V8_INDEX_SHA256 = (
    "75737e6175f4de03f84e9b0cead12e92cf5fcdfa9e59a85ba845bd0a7fa60bd4"
)
OPEN_SEED_V13_MANIFEST_SHA256 = (
    "3aace8621b42d4026a534afca64de9181af21e98c581867a9bebf8ec5bdf96f7"
)
OPEN_SEED_V20_MANIFEST_SHA256 = (
    "e45aeeddc2d450a9faebf9f8919e3726dadf2547c95a864c395c75c95302c456"
)
PUBLIC_FEDERATION_V9_MANIFEST_SHA256 = (
    "9dee9fc48ce8dd4d729bbd45fec7d976f79af041894ecb1ef5a9401f7f4f04c5"
)
PUBLIC_FEDERATION_V9_INDEX_SHA256 = (
    "600b34d8807fa06b2ea2e098c39f72d2299a8a485ae08a41b66c9b334bdc4cb1"
)
PUBLIC_COVERAGE_V10_DEFINITION = (
    ROOT / "sources" / "coverage-audit-2026-07-19-public-open-v10.json"
)
PUBLIC_COVERAGE_V10_DEFINITION_SHA256 = (
    "17dbc93024e49a9a12af31452c4c97a7c521e612472462031fe3a76deb817eee"
)
PUBLIC_COVERAGE_V10 = ROOT / "audits" / "2026-07-19-public-open-coverage-v10"
PUBLIC_COVERAGE_V10_MANIFEST_SHA256 = (
    "ef874db51e442cee124c47316ccb0bc075121ad47e43e248f6e4d294c577f83e"
)
PUBLIC_COVERAGE_V10_ARTIFACTS = {
    "REPORT.md": {
        "bytes": 4_147,
        "sha256": "2a2917c9361c2971d8ba75b81b0bf469b7b2ab27a910526b2aa34b258f962bc4",
    },
    "coverage-audit.json": {
        "bytes": 1_199_853,
        "sha256": "b4933c06e394dfd31d627553dbcb8d3e452ba50501276b59ebacab7e46a8aeb9",
    },
    "coverage.csv": {
        "bytes": 163_491,
        "sha256": "34fdd401cf74d37b8e8d52f4094c8a182ef35dc996c2decf2cc3e1268e293379",
    },
    "gap-registry.json": {
        "bytes": 1_060_901,
        "sha256": "db5e2e925e9026027fe6f95162c3a04fc9a08bd9e9074e5ef0b044717264435b",
    },
}


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _csv_bytes(fieldnames: list[str], rows: list[dict[str, object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def _write_release(
    path: Path,
    *,
    source_family: str,
    entity_kind: str,
    review_only: bool,
    feature: dict[str, object],
    resolution_candidates: int = 0,
) -> str:
    path.mkdir()
    evidence_id = "evidence-1"
    files = {
        "ATTRIBUTION.txt": f"Attribution for {source_family}\n".encode(),
        "atlas.geojson": _json_bytes(
            {
                "features": [
                    {
                        "geometry": None,
                        "id": feature["entity_id"],
                        "properties": feature,
                        "type": "Feature",
                    }
                ],
                "type": "FeatureCollection",
            }
        ),
        "entities.csv": _csv_bytes(
            ["entity_id", "entity_kind"],
            [
                {
                    "entity_id": feature["entity_id"],
                    "entity_kind": entity_kind,
                }
            ],
        ),
        "evidence.csv": _csv_bytes(
            ["evidence_id", "source_family", "license"],
            [
                {
                    "evidence_id": evidence_id,
                    "source_family": source_family,
                    "license": "CC0-1.0",
                }
            ],
        ),
        "source_inputs.json": _json_bytes({"source_family": source_family}),
    }
    for filename, raw in files.items():
        (path / filename).write_bytes(raw)
    capacity_count = len(feature.get("capacity_estimates", []))
    manifest: dict[str, object] = {
        "as_of": "2026-07-18",
        "capacity_estimates": capacity_count,
        "construction_pipeline_records": int(
            feature.get("status") in {"under_construction", "proposed"}
        ),
        "entities": 1,
        "entities_by_kind": {entity_kind: 1},
        "evidence_records": 1,
        "files": {
            filename: {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            for filename, raw in sorted(files.items())
        },
        "format": "datacenter-atlas-release-v1",
        "recorded_at": "2026-07-18T20:00:00Z",
        "resolution_candidates": resolution_candidates,
        "source_families": [source_family],
    }
    if review_only:
        manifest["review_only"] = True
    raw = _json_bytes(manifest)
    (path / "manifest.json").write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _feature(
    entity_id: str,
    source_family: str,
    entity_kind: str,
    *,
    status: str | None,
    country: str | None,
    coordinates: bool,
    annual_energy: bool = False,
    operating_model: str | None = None,
    workload: str | None = None,
) -> dict[str, object]:
    evidence_id = "evidence-1"
    capacities: list[dict[str, object]] = []
    if annual_energy:
        capacities.append(
            {
                "confidence": 0.5,
                "evidence_id": evidence_id,
                "method": "modeled",
                "metric": "annual_energy_mwh",
                "stage": "forecast",
            }
        )
    workloads = [workload] if workload else []
    workload_observations = (
        [
            {
                "confidence": 0.6,
                "evidence_id": evidence_id,
                "method": "reported",
                "workload": workload,
            }
        ]
        if workload
        else []
    )
    result: dict[str, object] = {
        "capacity_estimates": capacities,
        "entity_id": entity_id,
        "entity_kind": entity_kind,
        "latitude": 38.0 if coordinates else None,
        "longitude": -77.0 if coordinates else None,
        "operating_model": operating_model,
        "operating_model_evidence_id": evidence_id if operating_model else None,
        "source_family": source_family,
        "status": status,
        "status_as_of": "2026-07-17" if status else None,
        "status_evidence_id": evidence_id if status else None,
        "status_method": "reported" if status else None,
        "tags": {"country": country} if country else {},
        "workload_observations": workload_observations,
        "workloads": workloads,
    }
    return result


def _benchmark() -> dict[str, object]:
    claims = [
        ("capacity_outputs", "methodology"),
        ("construction_timeline_pjm", "methodology"),
        ("evidence_methodology", "methodology"),
        ("facility_scope_count", "count"),
        ("temporal_granularity", "coverage"),
    ]
    return {
        "claims": [
            {
                "claim_id": claim_id,
                "kind": kind,
                "paraphrase": f"Public claim {claim_id}.",
                "source_url": "https://semianalysis.com/models-research/",
            }
            for claim_id, kind in claims
        ],
        "name": "SemiAnalysis public claims",
        "retrieved_on": "2026-07-18",
    }


class CoverageAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        releases = self.root / "releases"
        releases.mkdir()
        children = [
            (
                "epoch-seed",
                "epoch",
                "campus",
                False,
                _feature(
                    "seed-1",
                    "epoch",
                    "campus",
                    status="under_construction",
                    country="United States",
                    coordinates=True,
                    annual_energy=True,
                    operating_model="hyperscale_lease",
                    workload="ai_specialized_unspecified",
                ),
                0,
            ),
            (
                "global-open",
                "osm",
                "building",
                False,
                _feature(
                    "global-1",
                    "osm",
                    "building",
                    status=None,
                    country=None,
                    coordinates=False,
                ),
                2,
            ),
            (
                "review-leads",
                "osm:fuzzy",
                "facility",
                True,
                _feature(
                    "review-1",
                    "osm:fuzzy",
                    "facility",
                    status="under_construction",
                    country="China",
                    coordinates=True,
                ),
                0,
            ),
        ]
        child_definitions = []
        audit_children = []
        for release_id, source, kind, review, feature, candidates in children:
            release_path = releases / release_id
            digest = _write_release(
                release_path,
                source_family=source,
                entity_kind=kind,
                review_only=review,
                feature=feature,
                resolution_candidates=candidates,
            )
            child_definitions.append(
                {
                    "expected_manifest_sha256": digest,
                    "license_expression": "CC0-1.0",
                    "reference": f"../{release_id}/",
                    "release_id": release_id,
                    "release_path": str(release_path),
                    "rights_notice": f"Rights for {release_id}.",
                }
            )
            audit_children.append(
                {
                    "expected_manifest_sha256": digest,
                    "release_id": release_id,
                    "release_path": str(release_path),
                }
            )
        self.child_definitions = child_definitions
        self.audit_children = audit_children
        federation_definition = self.root / "federation.json"
        federation_definition.write_bytes(
            _json_bytes(
                {
                    "children": child_definitions,
                    "generated_at": "2026-07-18T20:00:00Z",
                    "schema_version": 1,
                }
            )
        )
        self.federation = self.root / "federation"
        write_federated_release_index(federation_definition, self.federation)
        federation_manifest = (self.federation / "manifest.json").read_bytes()
        self.definition = self.root / "audit-definition.json"
        self.definition.write_bytes(
            _json_bytes(
                {
                    "audit_id": "test-coverage-v1",
                    "children": audit_children,
                    "federated_index": {
                        "expected_manifest_sha256": hashlib.sha256(
                            federation_manifest
                        ).hexdigest(),
                        "path": str(self.federation),
                    },
                    "generated_at": "2026-07-18T20:20:00Z",
                    "public_benchmark": _benchmark(),
                    "schema_version": 1,
                }
            )
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_build_separates_candidates_and_unknown_physical_counts(self) -> None:
        bundle = build_coverage_audit(self.definition)
        totals = bundle.audit["totals"]
        self.assertEqual(totals["source_scoped_entity_records"], 3)
        self.assertEqual(totals["non_review_source_scoped_entity_records"], 2)
        self.assertEqual(totals["review_only_source_scoped_entity_records"], 1)
        self.assertEqual(totals["advisory_resolution_candidate_records"], 2)
        self.assertIsNone(totals["confirmed_duplicate_relationships"])
        self.assertIsNone(totals["unique_physical_sites"])
        fields = totals["field_totals"]
        self.assertEqual(
            fields["non_review_source_declared_entity_kind_counts"],
            {"building": 1, "campus": 1},
        )
        self.assertEqual(fields["source_declared_entity_kind_counts"]["facility"], 1)
        self.assertEqual(fields["non_review_under_construction_rows"], 1)
        self.assertEqual(fields["review_only_under_construction_lead_rows"], 1)
        self.assertEqual(
            fields["annual_energy_provenance_counts"],
            {"modeled|epoch|CC0-1.0": 1},
        )
        comparison = bundle.audit["semianalysis_public_comparison"]
        self.assertEqual(comparison["overall_parity"]["status"], "pending")
        self.assertEqual(
            comparison["licensed_row_level_benchmark"]["status"], "pending"
        )
        methodology = next(
            item
            for item in comparison["comparisons"]
            if item["claim_id"] == "evidence_methodology"
        )["atlas_evidence"]
        self.assertEqual(
            methodology["permits"], "absent_from_audited_children"
        )

    def test_explicit_methodology_references_are_exact_and_transparent(self) -> None:
        document = json.loads(self.definition.read_text(encoding="utf-8"))
        document["methodology_evidence_classification"] = {
            "computer_vision": [],
            "foia": [],
            "permits": [
                {
                    "evidence_id": "evidence-1",
                    "release_id": "epoch-seed",
                }
            ],
            "property_records": [],
            "satellite_imagery": [],
        }
        definition = self.root / "audit-definition-methodology.json"
        definition.write_bytes(_json_bytes(document))

        bundle = build_coverage_audit(definition)

        methodology = next(
            item
            for item in bundle.audit["semianalysis_public_comparison"][
                "comparisons"
            ]
            if item["claim_id"] == "evidence_methodology"
        )["atlas_evidence"]
        self.assertEqual(
            methodology["permits"],
            {
                "status": "permitting_process_evidence_present",
                "evidence_reference_count": 1,
                "evidence_ids": ["evidence-1"],
                "release_ids": ["epoch-seed"],
                "source_families": ["epoch"],
                "evidence_references": [
                    {
                        "evidence_id": "evidence-1",
                        "release_id": "epoch-seed",
                        "source_family": "epoch",
                    }
                ],
                "scope_guardrail": (
                    "References document permitting processes only; classification "
                    "does not assert a granted permit, project approval, or physical "
                    "construction."
                ),
            },
        )
        self.assertEqual(
            methodology["property_records"],
            {
                "status": "absent_from_audited_children",
                "evidence_reference_count": 0,
                "evidence_ids": [],
                "release_ids": [],
                "source_families": [],
                "evidence_references": [],
            },
        )
        self.assertEqual(
            methodology["power_data"],
            {
                "status": "partial_capacity_observations_present",
                "capacity_observation_count": 1,
                "capacity_observations_with_resolved_evidence": 1,
            },
        )

    def test_methodology_reference_schema_and_exact_existence_fail_closed(self) -> None:
        base = json.loads(self.definition.read_text(encoding="utf-8"))
        classification = {
            "computer_vision": [],
            "foia": [],
            "permits": [
                {
                    "evidence_id": "evidence-1",
                    "release_id": "epoch-seed",
                }
            ],
            "property_records": [],
            "satellite_imagery": [],
        }

        unknown_category = {
            **base,
            "methodology_evidence_classification": classification,
        }
        unknown_category["methodology_evidence_classification"] = {
            **classification,
            "titles_containing_permit": [],
        }
        unknown_category_path = self.root / "unknown-category.json"
        unknown_category_path.write_bytes(_json_bytes(unknown_category))
        with self.assertRaisesRegex(CoverageAuditError, "schema is invalid"):
            build_coverage_audit(unknown_category_path)

        duplicate = {**base, "methodology_evidence_classification": classification}
        duplicate["methodology_evidence_classification"] = {
            **classification,
            "permits": [classification["permits"][0], classification["permits"][0]],
        }
        duplicate_path = self.root / "duplicate-reference.json"
        duplicate_path.write_bytes(_json_bytes(duplicate))
        with self.assertRaisesRegex(CoverageAuditError, "sorted and unique"):
            build_coverage_audit(duplicate_path)

        unknown_release = {
            **base,
            "methodology_evidence_classification": {
                **classification,
                "permits": [
                    {
                        "evidence_id": "evidence-1",
                        "release_id": "not-a-child",
                    }
                ],
            },
        }
        unknown_release_path = self.root / "unknown-release.json"
        unknown_release_path.write_bytes(_json_bytes(unknown_release))
        with self.assertRaisesRegex(CoverageAuditError, "unknown coverage children"):
            build_coverage_audit(unknown_release_path)

        unknown_evidence = {
            **base,
            "methodology_evidence_classification": {
                **classification,
                "permits": [
                    {
                        "evidence_id": "not-evidence",
                        "release_id": "epoch-seed",
                    }
                ],
            },
        }
        unknown_evidence_path = self.root / "unknown-evidence.json"
        unknown_evidence_path.write_bytes(_json_bytes(unknown_evidence))
        with self.assertRaisesRegex(
            CoverageAuditError, "does not exist in exact child"
        ):
            build_coverage_audit(unknown_evidence_path)

    def test_groups_and_gap_registry_are_machine_readable(self) -> None:
        bundle = build_coverage_audit(self.definition)
        groups = bundle.audit["groups"]
        self.assertEqual(len([g for g in groups if g["scope_type"] == "release"]), 3)
        unresolved = [
            group
            for group in groups
            if group["scope_type"] == "release_source_country"
            and group["country"] == "__UNRESOLVED__"
        ]
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["coordinate_coverage"], 0.0)
        review = next(
            group
            for group in groups
            if group["scope_type"] == "release" and group["release_review_only"]
        )
        self.assertEqual(review["non_review_source_declared_entity_kind_counts"], {})
        gap_fields = {gap["field"] for gap in bundle.gaps["gaps"]}
        self.assertIn("unique_physical_sites", gap_fields)
        self.assertIn("licensed_row_level_benchmark", gap_fields)
        self.assertIn("coordinates", gap_fields)
        self.assertEqual(
            bundle.gaps["summary"]["open_gaps"], len(bundle.gaps["gaps"])
        )

    def test_scope_and_report_derive_scrutica_inclusion(self) -> None:
        release_id = "scrutica-review"
        release_path = self.root / "releases" / release_id
        digest = _write_release(
            release_path,
            source_family="scrutica",
            entity_kind="facility",
            review_only=True,
            feature=_feature(
                "scrutica-1",
                "scrutica",
                "facility",
                status="announced",
                country="United States",
                coordinates=True,
            ),
        )
        federation_definition = self.root / "federation-scrutica.json"
        child_definitions = sorted(
            [
                *self.child_definitions,
                {
                    "expected_manifest_sha256": digest,
                    "license_expression": "CC-BY-SA-4.0",
                    "reference": f"../{release_id}/",
                    "release_id": release_id,
                    "release_path": str(release_path),
                    "rights_notice": "Rights for Scrutica review rows.",
                },
            ],
            key=lambda child: child["release_id"],
        )
        federation_definition.write_bytes(
            _json_bytes(
                {
                    "children": child_definitions,
                    "generated_at": "2026-07-18T20:10:00Z",
                    "schema_version": 1,
                }
            )
        )
        federation = self.root / "federation-scrutica"
        write_federated_release_index(federation_definition, federation)
        definition = self.root / "audit-definition-scrutica.json"
        audit_children = sorted(
            [
                *self.audit_children,
                {
                    "expected_manifest_sha256": digest,
                    "release_id": release_id,
                    "release_path": str(release_path),
                },
            ],
            key=lambda child: child["release_id"],
        )
        definition.write_bytes(
            _json_bytes(
                {
                    "audit_id": "test-scrutica-coverage-v1",
                    "children": audit_children,
                    "federated_index": {
                        "expected_manifest_sha256": hashlib.sha256(
                            (federation / "manifest.json").read_bytes()
                        ).hexdigest(),
                        "path": str(federation),
                    },
                    "generated_at": "2026-07-18T20:20:00Z",
                    "public_benchmark": _benchmark(),
                    "schema_version": 1,
                }
            )
        )

        bundle = build_coverage_audit(definition)

        self.assertTrue(bundle.audit["scope"]["scrutica_included"])
        self.assertFalse(
            bundle.audit["scope"]["provisional_open_layer_audit"]
        )
        self.assertIn(
            "including review-only Scrutica rows",
            bundle.payloads["REPORT.md"].decode("utf-8"),
        )

    def test_atomic_write_validate_and_idempotent_rebuild(self) -> None:
        output = self.root / "audit"
        write_coverage_audit(self.definition, output)
        before = {path.name: path.read_bytes() for path in output.iterdir()}
        validated = validate_coverage_audit(
            output, definition_path=self.definition
        )
        self.assertEqual(validated["audit_id"], "test-coverage-v1")
        write_coverage_audit(self.definition, output)
        after = {path.name: path.read_bytes() for path in output.iterdir()}
        self.assertEqual(before, after)
        with (output / COVERAGE_CSV_FILENAME).open(
            "r", encoding="utf-8", newline=""
        ) as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), len(validated["groups"]))
        self.assertTrue((output / AUDIT_FILENAME).is_file())
        self.assertTrue((output / GAP_REGISTRY_FILENAME).is_file())

    def test_tampering_and_input_drift_fail_closed(self) -> None:
        output = self.root / "audit"
        write_coverage_audit(self.definition, output)
        csv_path = output / COVERAGE_CSV_FILENAME
        csv_path.write_bytes(csv_path.read_bytes() + b"tamper\n")
        with self.assertRaisesRegex(CoverageAuditError, "checkpoint mismatch"):
            validate_coverage_audit(output)
        with self.assertRaises(CoverageAuditError):
            write_coverage_audit(self.definition, output)

        bundle = build_coverage_audit(self.definition)
        definition = json.loads(self.definition.read_text())
        definition["children"][0]["expected_manifest_sha256"] = "0" * 64
        drifted = self.root / "drifted.json"
        drifted.write_bytes(_json_bytes(definition))
        with self.assertRaisesRegex(CoverageAuditError, "does not match audit definition"):
            build_coverage_audit(drifted)
        self.assertEqual(bundle.audit["scope"]["candidate_rows_counted_as_facilities"], False)


class FrozenPublicCoverageV5Tests(unittest.TestCase):
    def test_current_public_audit_rebuilds_offline_and_is_frozen(self) -> None:
        with patch.object(
            socket, "socket", side_effect=AssertionError("network used")
        ):
            audit = validate_coverage_audit(
                PUBLIC_COVERAGE_V5,
                definition_path=PUBLIC_COVERAGE_V5_DEFINITION,
            )
        self.assertEqual(audit["totals"]["source_scoped_entity_records"], 15_529)
        self.assertEqual(audit["totals"]["non_review_source_scoped_entity_records"], 9_399)
        self.assertEqual(len(audit["groups"]), 256)
        gaps = json.loads(
            (PUBLIC_COVERAGE_V5 / GAP_REGISTRY_FILENAME).read_text(encoding="utf-8")
        )["gaps"]
        self.assertEqual(len(gaps), 1_536)
        self.assertEqual(
            hashlib.sha256(
                (PUBLIC_COVERAGE_V5 / "manifest.json").read_bytes()
            ).hexdigest(),
            PUBLIC_COVERAGE_V5_MANIFEST_SHA256,
        )
        self.assertEqual(stat.S_IMODE(PUBLIC_COVERAGE_V5.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in PUBLIC_COVERAGE_V5.iterdir()
            )
        )


class FrozenPublicCoverageV6Tests(unittest.TestCase):
    def test_current_public_audit_rebuilds_offline_and_is_frozen(self) -> None:
        with patch.object(
            socket, "socket", side_effect=AssertionError("network used")
        ):
            audit = validate_coverage_audit(
                PUBLIC_COVERAGE_V6,
                definition_path=PUBLIC_COVERAGE_V6_DEFINITION,
            )
        self.assertEqual(audit["totals"]["source_scoped_entity_records"], 15_537)
        self.assertEqual(
            audit["totals"]["non_review_source_scoped_entity_records"], 9_407
        )
        self.assertEqual(len(audit["groups"]), 263)
        gaps = json.loads(
            (PUBLIC_COVERAGE_V6 / GAP_REGISTRY_FILENAME).read_text(encoding="utf-8")
        )["gaps"]
        self.assertEqual(len(gaps), 1_561)
        self.assertIsNone(audit["totals"]["unique_physical_sites"])
        self.assertEqual(
            hashlib.sha256(
                (PUBLIC_COVERAGE_V6 / "manifest.json").read_bytes()
            ).hexdigest(),
            PUBLIC_COVERAGE_V6_MANIFEST_SHA256,
        )
        self.assertEqual(stat.S_IMODE(PUBLIC_COVERAGE_V6.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in PUBLIC_COVERAGE_V6.iterdir()
            )
        )


class FrozenPublicCoverageV7Tests(unittest.TestCase):
    def test_current_public_audit_rebuilds_offline_and_is_frozen(self) -> None:
        with patch.object(
            socket, "socket", side_effect=AssertionError("network used")
        ):
            audit = validate_coverage_audit(
                PUBLIC_COVERAGE_V7,
                definition_path=PUBLIC_COVERAGE_V7_DEFINITION,
            )
        self.assertEqual(audit["totals"]["source_scoped_entity_records"], 15_552)
        self.assertEqual(
            audit["totals"]["non_review_source_scoped_entity_records"], 9_422
        )
        self.assertEqual(len(audit["groups"]), 278)
        gaps = json.loads(
            (PUBLIC_COVERAGE_V7 / GAP_REGISTRY_FILENAME).read_text(encoding="utf-8")
        )["gaps"]
        self.assertEqual(len(gaps), 1_611)
        self.assertIsNone(audit["totals"]["unique_physical_sites"])
        self.assertEqual(
            hashlib.sha256(
                (PUBLIC_COVERAGE_V7 / "manifest.json").read_bytes()
            ).hexdigest(),
            PUBLIC_COVERAGE_V7_MANIFEST_SHA256,
        )
        self.assertEqual(stat.S_IMODE(PUBLIC_COVERAGE_V7.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in PUBLIC_COVERAGE_V7.iterdir()
            )
        )


class FrozenPublicCoverageV8Tests(unittest.TestCase):
    def test_current_public_audit_rebuilds_offline_and_is_frozen(self) -> None:
        with patch.object(
            socket, "socket", side_effect=AssertionError("network used")
        ):
            audit = validate_coverage_audit(
                PUBLIC_COVERAGE_V8,
                definition_path=PUBLIC_COVERAGE_V8_DEFINITION,
            )
        self.assertEqual(audit["totals"]["source_scoped_entity_records"], 15_552)
        self.assertEqual(
            audit["totals"]["non_review_source_scoped_entity_records"], 9_422
        )
        self.assertEqual(len(audit["groups"]), 278)
        gaps = json.loads(
            (PUBLIC_COVERAGE_V8 / GAP_REGISTRY_FILENAME).read_text(encoding="utf-8")
        )["gaps"]
        self.assertEqual(len(gaps), 1_611)
        self.assertIsNone(audit["totals"]["unique_physical_sites"])
        methodology = next(
            item
            for item in audit["semianalysis_public_comparison"]["comparisons"]
            if item["claim_id"] == "evidence_methodology"
        )["atlas_evidence"]
        self.assertEqual(methodology["permits"]["evidence_reference_count"], 4)
        self.assertEqual(
            methodology["permits"]["status"],
            "permitting_process_evidence_present",
        )
        self.assertEqual(methodology["power_data"]["capacity_observation_count"], 1_134)
        self.assertEqual(
            hashlib.sha256(
                (PUBLIC_COVERAGE_V8 / "manifest.json").read_bytes()
            ).hexdigest(),
            PUBLIC_COVERAGE_V8_MANIFEST_SHA256,
        )
        self.assertEqual(stat.S_IMODE(PUBLIC_COVERAGE_V8.stat().st_mode), 0o555)
        self.assertTrue(
            all(
                stat.S_IMODE(path.stat().st_mode) == 0o444
                for path in PUBLIC_COVERAGE_V8.iterdir()
            )
        )


class PublicCoverageV9Tests(unittest.TestCase):
    OLD_OPEN_RELEASE_ID = "epoch-official-open-seed-v9"
    NEW_OPEN_RELEASE_ID = "epoch-official-open-seed-v13"

    @classmethod
    def normalize_open_release_id(cls, value: object) -> object:
        if isinstance(value, dict):
            return {
                key: cls.normalize_open_release_id(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls.normalize_open_release_id(item) for item in value]
        if value == cls.NEW_OPEN_RELEASE_ID:
            return cls.OLD_OPEN_RELEASE_ID
        return value

    @classmethod
    def group_key(cls, group: dict[str, object]) -> tuple[object, ...]:
        normalized = cls.normalize_open_release_id(group)
        assert isinstance(normalized, dict)
        return (
            normalized["child_release"],
            normalized["scope_type"],
            normalized["source_family"],
            normalized["country"],
            normalized["country_iso_a2"],
            normalized["country_iso_a3"],
        )

    @classmethod
    def gap_key(cls, gap: dict[str, object]) -> tuple[object, ...]:
        normalized = cls.normalize_open_release_id(gap)
        assert isinstance(normalized, dict)
        return (
            normalized["scope_type"],
            normalized["child_release"],
            normalized["source_family"],
            normalized["country"],
            normalized["field"],
        )

    @staticmethod
    def normalized_gap(gap: dict[str, object]) -> dict[str, object]:
        normalized = PublicCoverageV9Tests.normalize_open_release_id(gap)
        assert isinstance(normalized, dict)
        normalized.pop("gap_id")
        return normalized

    @staticmethod
    def require_frozen_release_modes(directory: Path) -> None:
        if directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode) != 0o555:
            raise CoverageAuditError("release directory mode must be 0555")
        for path in directory.iterdir():
            if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o444:
                raise CoverageAuditError("release file mode must be 0444")

    @staticmethod
    def absolute_candidate_definition() -> dict[str, object]:
        definition = json.loads(
            PUBLIC_COVERAGE_V9_DEFINITION.read_text(encoding="utf-8")
        )
        definition_root = PUBLIC_COVERAGE_V9_DEFINITION.parent
        definition["federated_index"]["path"] = str(
            (definition_root / definition["federated_index"]["path"]).resolve()
        )
        for child in definition["children"]:
            child["release_path"] = str(
                (definition_root / child["release_path"]).resolve()
            )
        return definition

    def test_accepted_release_rebuilds_twice_offline_with_exact_preservation_deltas(self) -> None:
        self.assertEqual(
            hashlib.sha256(PUBLIC_COVERAGE_V9_DEFINITION.read_bytes()).hexdigest(),
            PUBLIC_COVERAGE_V9_DEFINITION_SHA256,
        )
        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline validator attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("offline validator attempted network access"),
        ):
            first = validate_coverage_audit(
                PUBLIC_COVERAGE_V9,
                definition_path=PUBLIC_COVERAGE_V9_DEFINITION,
            )
            second = validate_coverage_audit(
                PUBLIC_COVERAGE_V9,
                definition_path=PUBLIC_COVERAGE_V9_DEFINITION,
            )
        self.assertEqual(first, second)
        self.assertEqual(
            hashlib.sha256((PUBLIC_COVERAGE_V9 / "manifest.json").read_bytes())
            .hexdigest(),
            PUBLIC_COVERAGE_V9_MANIFEST_SHA256,
        )
        self.assertEqual(
            first["inputs"]["federated_index"]["manifest"]["sha256"],
            PUBLIC_FEDERATION_V8_MANIFEST_SHA256,
        )
        self.assertEqual(
            first["inputs"]["federated_index"]["index"]["sha256"],
            PUBLIC_FEDERATION_V8_INDEX_SHA256,
        )

        previous = json.loads(
            (PUBLIC_COVERAGE_V8 / AUDIT_FILENAME).read_text(encoding="utf-8")
        )
        previous_gaps = json.loads(
            (PUBLIC_COVERAGE_V8 / GAP_REGISTRY_FILENAME).read_text(encoding="utf-8")
        )
        current_gaps = json.loads(
            (PUBLIC_COVERAGE_V9 / GAP_REGISTRY_FILENAME).read_text(encoding="utf-8")
        )
        previous_definition = json.loads(
            PUBLIC_COVERAGE_V8_DEFINITION.read_text(encoding="utf-8")
        )
        current_definition = json.loads(
            PUBLIC_COVERAGE_V9_DEFINITION.read_text(encoding="utf-8")
        )

        self.assertEqual(
            current_definition["public_benchmark"],
            previous_definition["public_benchmark"],
        )
        self.assertEqual(
            self.normalize_open_release_id(
                current_definition["methodology_evidence_classification"]
            ),
            previous_definition["methodology_evidence_classification"],
        )
        previous_children = {
            child["release_id"]: child for child in previous_definition["children"]
        }
        current_children = {
            child["release_id"]: child for child in current_definition["children"]
        }
        self.assertEqual(
            set(current_children),
            (set(previous_children) - {self.OLD_OPEN_RELEASE_ID})
            | {self.NEW_OPEN_RELEASE_ID},
        )
        self.assertNotIn(self.OLD_OPEN_RELEASE_ID, current_children)
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(current_children[release_id], previous_children[release_id])
        self.assertEqual(
            current_children[self.NEW_OPEN_RELEASE_ID]["expected_manifest_sha256"],
            OPEN_SEED_V13_MANIFEST_SHA256,
        )

        expected_total_deltas = {
            "advisory_resolution_candidate_records": 1,
            "non_review_source_scoped_entity_records": 67,
            "review_only_source_scoped_entity_records": 0,
            "source_scoped_entity_records": 67,
        }
        for field, delta in expected_total_deltas.items():
            self.assertEqual(first["totals"][field] - previous["totals"][field], delta)
        self.assertEqual(first["totals"]["source_scoped_entity_records"], 15_619)
        self.assertEqual(
            first["totals"]["non_review_source_scoped_entity_records"], 9_489
        )
        self.assertEqual(
            first["totals"]["review_only_source_scoped_entity_records"], 6_130
        )
        self.assertEqual(first["totals"]["advisory_resolution_candidate_records"], 100_409)
        self.assertIsNone(first["totals"]["confirmed_duplicate_relationships"])
        self.assertIsNone(first["totals"]["unique_physical_sites"])

        field_delta = {
            field: first["totals"]["field_totals"][field]
            - previous["totals"]["field_totals"][field]
            for field in (
                "capacity_entity_rows",
                "capacity_observations",
                "complete_lifecycle_claim_rows",
                "construction_evidence_observations",
                "coordinate_rows",
                "country_rows",
                "informative_lifecycle_status_rows",
                "lifecycle_status_rows",
                "non_review_under_construction_rows",
                "pipeline_rows",
                "source_scoped_rows",
                "under_construction_rows",
                "unresolved_lifecycle_status_rows",
            )
        }
        self.assertEqual(
            field_delta,
            {
                "capacity_entity_rows": 13,
                "capacity_observations": 14,
                "complete_lifecycle_claim_rows": 34,
                "construction_evidence_observations": 14,
                "coordinate_rows": 10,
                "country_rows": 67,
                "informative_lifecycle_status_rows": 34,
                "lifecycle_status_rows": 34,
                "non_review_under_construction_rows": 16,
                "pipeline_rows": 16,
                "source_scoped_rows": 67,
                "under_construction_rows": 16,
                "unresolved_lifecycle_status_rows": 33,
            },
        )

        previous_groups = {
            self.group_key(group): group for group in previous["groups"]
        }
        current_groups = {self.group_key(group): group for group in first["groups"]}
        self.assertEqual(set(previous_groups) - set(current_groups), set())
        added_group_keys = set(current_groups) - set(previous_groups)
        self.assertEqual(len(added_group_keys), 42)
        self.assertEqual(
            Counter(key[1] for key in added_group_keys),
            {"release_source": 16, "release_source_country": 26},
        )
        changed_common_groups = {
            key
            for key in previous_groups.keys() & current_groups.keys()
            if previous_groups[key]
            != self.normalize_open_release_id(current_groups[key])
        }
        self.assertEqual(
            changed_common_groups,
            {
                (
                    self.OLD_OPEN_RELEASE_ID,
                    "release",
                    "__ALL__",
                    "__ALL__",
                    None,
                    None,
                ),
                (
                    self.OLD_OPEN_RELEASE_ID,
                    "release_source",
                    "microsoft_official_news",
                    "__ALL__",
                    None,
                    None,
                ),
            },
        )

        previous_gap_rows = {
            self.gap_key(gap): gap for gap in previous_gaps["gaps"]
        }
        current_gap_rows = {
            self.gap_key(gap): gap for gap in current_gaps["gaps"]
        }
        self.assertEqual(set(previous_gap_rows) - set(current_gap_rows), set())
        self.assertEqual(len(current_gap_rows) - len(previous_gap_rows), 208)
        for key in previous_gap_rows.keys() & current_gap_rows.keys():
            self.assertEqual(
                self.normalized_gap(current_gap_rows[key]),
                self.normalized_gap(previous_gap_rows[key]),
            )
        previous_field_counts = Counter(
            gap["field"] for gap in previous_gaps["gaps"]
        )
        current_field_counts = Counter(gap["field"] for gap in current_gaps["gaps"])
        self.assertEqual(
            current_field_counts - previous_field_counts,
            {
                "annual_energy": 26,
                "capacity": 21,
                "coordinates": 23,
                "informative_lifecycle_status": 21,
                "lifecycle_status": 21,
                "operating_model": 26,
                "source_scoped_rows": 2,
                "status_as_of": 21,
                "status_evidence": 21,
                "workload": 26,
            },
        )
        previous_severity_counts = Counter(
            gap["severity"] for gap in previous_gaps["gaps"]
        )
        current_severity_counts = Counter(
            gap["severity"] for gap in current_gaps["gaps"]
        )
        self.assertEqual(
            current_severity_counts - previous_severity_counts,
            {"high": 23, "info": 2, "low": 99, "medium": 84},
        )

        previous_comparison = previous["semianalysis_public_comparison"]
        current_comparison = first["semianalysis_public_comparison"]
        self.assertEqual(
            current_comparison["benchmark"], previous_comparison["benchmark"]
        )
        self.assertEqual(
            current_comparison["licensed_row_level_benchmark"],
            previous_comparison["licensed_row_level_benchmark"],
        )
        self.assertEqual(
            current_comparison["overall_parity"],
            previous_comparison["overall_parity"],
        )
        previous_by_claim = {
            comparison["claim_id"]: comparison
            for comparison in previous_comparison["comparisons"]
        }
        current_by_claim = {
            comparison["claim_id"]: comparison
            for comparison in current_comparison["comparisons"]
        }
        for claim_id in previous_by_claim:
            self.assertEqual(
                (
                    current_by_claim[claim_id]["atlas_status"],
                    current_by_claim[claim_id]["parity_status"],
                ),
                (
                    previous_by_claim[claim_id]["atlas_status"],
                    previous_by_claim[claim_id]["parity_status"],
                ),
            )
        methodology = current_by_claim["evidence_methodology"]["atlas_evidence"]
        self.assertEqual(methodology["permits"]["evidence_reference_count"], 4)
        self.assertEqual(
            methodology["permits"]["status"],
            "permitting_process_evidence_present",
        )
        self.assertEqual(methodology["power_data"]["capacity_observation_count"], 1_148)
        self.assertEqual(
            methodology["power_data"]["capacity_observations_with_resolved_evidence"],
            1_148,
        )

        self.assertEqual(first["scope"], previous["scope"])
        self.assertFalse(first["scope"]["children_merged"])
        self.assertFalse(first["scope"]["cross_source_deduplication"])
        self.assertFalse(first["scope"]["review_candidates_promoted"])
        self.assertFalse(first["scope"]["candidate_rows_counted_as_facilities"])
        self.assertIsNone(first["scope"]["confirmed_duplicate_relationships"])
        self.assertIsNone(first["scope"]["unique_physical_sites"])

        atlas = json.loads(
            (ROOT / "releases" / "2026-07-19-open-seed-v13" / "atlas.geojson")
            .read_text(encoding="utf-8")
        )
        qts_cedar = {
            feature["properties"]["stable_key"]: feature["properties"]["entity_id"]
            for feature in atlas["features"]
            if "QTS Cedar Rapids" in feature["properties"]["name"]
        }
        self.assertEqual(
            set(qts_cedar),
            {
                "curated:qts-cedar-rapids-data-center-campus",
                "curated:qts-cedar-rapids-data-center-campus:current-campus-development",
                "epoch-ai:data-center:9e7c6b95-63aa-5bee-85fa-19ec052ede19",
            },
        )
        with (
            ROOT
            / "releases"
            / "2026-07-19-open-seed-v13"
            / "resolution_candidates.csv"
        ).open(encoding="utf-8", newline="") as stream:
            resolution_rows = list(csv.DictReader(stream))
        candidate_entity_ids = {
            row[field]
            for row in resolution_rows
            for field in ("left_entity_id", "right_entity_id")
        }
        self.assertTrue(set(qts_cedar.values()).isdisjoint(candidate_entity_ids))
        qts_us_group = next(
            group
            for group in first["groups"]
            if group["child_release"] == self.NEW_OPEN_RELEASE_ID
            and group["scope_type"] == "release_source_country"
            and group["source_family"] == "qts_data_center_location_pages"
            and group["country_iso_a2"] == "US"
        )
        self.assertEqual(
            {
                "source_scoped_rows": qts_us_group["source_scoped_rows"],
                "coordinate_rows": qts_us_group["coordinate_rows"],
                "lifecycle_status_rows": qts_us_group["lifecycle_status_rows"],
            },
            {
                "source_scoped_rows": 6,
                "coordinate_rows": 0,
                "lifecycle_status_rows": 3,
            },
        )
        qts_us_gap_fields = {
            gap["field"]
            for gap in current_gaps["gaps"]
            if gap["child_release"] == self.NEW_OPEN_RELEASE_ID
            and gap["source_family"] == "qts_data_center_location_pages"
            and gap["country"] == "United States"
        }
        self.assertEqual(
            qts_us_gap_fields,
            {
                "annual_energy",
                "capacity",
                "coordinates",
                "informative_lifecycle_status",
                "lifecycle_status",
                "operating_model",
                "status_as_of",
                "status_evidence",
                "workload",
            },
        )
        unique_site_gap = next(
            gap for gap in current_gaps["gaps"] if gap["field"] == "unique_physical_sites"
        )
        self.assertEqual(unique_site_gap["severity"], "high")

        self.assertEqual(stat.S_IMODE(PUBLIC_COVERAGE_V9_DEFINITION.stat().st_mode), 0o644)
        self.require_frozen_release_modes(PUBLIC_COVERAGE_V9)

    def test_release_copies_reject_wrong_pins_content_symlinks_and_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for case, field in (
                ("federation", None),
                ("child", "expected_manifest_sha256"),
            ):
                with self.subTest(case=case):
                    definition = self.absolute_candidate_definition()
                    if field is None:
                        definition["federated_index"][
                            "expected_manifest_sha256"
                        ] = "0" * 64
                        pattern = "federated index manifest SHA-256"
                    else:
                        open_child = next(
                            child
                            for child in definition["children"]
                            if child["release_id"] == self.NEW_OPEN_RELEASE_ID
                        )
                        open_child[field] = "0" * 64
                        pattern = "manifest SHA-256 does not match audit definition"
                    path = root / f"wrong-{case}.json"
                    path.write_bytes(_json_bytes(definition))
                    with self.assertRaisesRegex(CoverageAuditError, pattern):
                        build_coverage_audit(path)

            content_copy = root / "content-copy"
            shutil.copytree(PUBLIC_COVERAGE_V9, content_copy)
            content_copy.chmod(0o755)
            (content_copy / COVERAGE_CSV_FILENAME).chmod(0o644)
            with (content_copy / COVERAGE_CSV_FILENAME).open("ab") as stream:
                stream.write(b"tampered\n")
            with self.assertRaisesRegex(CoverageAuditError, "checkpoint mismatch"):
                validate_coverage_audit(content_copy)

            symlink_copy = root / "symlink-copy"
            shutil.copytree(PUBLIC_COVERAGE_V9, symlink_copy)
            symlink_copy.chmod(0o755)
            report = symlink_copy / "REPORT.md"
            report.chmod(0o644)
            report.unlink()
            report.symlink_to(PUBLIC_COVERAGE_V9 / "REPORT.md")
            with self.assertRaisesRegex(CoverageAuditError, "regular file"):
                validate_coverage_audit(symlink_copy)

            mode_copy = root / "mode-copy"
            shutil.copytree(PUBLIC_COVERAGE_V9, mode_copy)
            mode_copy.chmod(0o755)
            with self.assertRaisesRegex(CoverageAuditError, "mode must be 0555"):
                self.require_frozen_release_modes(mode_copy)


class FrozenPublicCoverageV10Tests(unittest.TestCase):
    OLD_OPEN_RELEASE_ID = "epoch-official-open-seed-v13"
    NEW_OPEN_RELEASE_ID = "epoch-official-open-seed-v20"

    @classmethod
    def normalize_open_release_id(cls, value: object) -> object:
        if isinstance(value, dict):
            return {
                key: cls.normalize_open_release_id(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls.normalize_open_release_id(item) for item in value]
        if value == cls.NEW_OPEN_RELEASE_ID:
            return cls.OLD_OPEN_RELEASE_ID
        return value

    @classmethod
    def group_key(cls, group: dict[str, object]) -> tuple[object, ...]:
        normalized = cls.normalize_open_release_id(group)
        assert isinstance(normalized, dict)
        return (
            normalized["child_release"],
            normalized["scope_type"],
            normalized["source_family"],
            normalized["country"],
            normalized["country_iso_a2"],
            normalized["country_iso_a3"],
        )

    @classmethod
    def gap_key(cls, gap: dict[str, object]) -> tuple[object, ...]:
        normalized = cls.normalize_open_release_id(gap)
        assert isinstance(normalized, dict)
        return (
            normalized["scope_type"],
            normalized["child_release"],
            normalized["source_family"],
            normalized["country"],
            normalized["field"],
        )

    @classmethod
    def normalized_gap(cls, gap: dict[str, object]) -> dict[str, object]:
        normalized = cls.normalize_open_release_id(gap)
        assert isinstance(normalized, dict)
        normalized.pop("gap_id")
        return normalized

    @staticmethod
    def require_frozen_modes(directory: Path) -> None:
        if directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode) != 0o555:
            raise CoverageAuditError("release directory mode must be 0555")
        for path in directory.iterdir():
            if (
                path.is_symlink()
                or not path.is_file()
                or stat.S_IMODE(path.stat().st_mode) != 0o444
            ):
                raise CoverageAuditError("release file mode must be 0444")

    @staticmethod
    def absolute_definition() -> dict[str, object]:
        definition = json.loads(
            PUBLIC_COVERAGE_V10_DEFINITION.read_text(encoding="utf-8")
        )
        definition_root = PUBLIC_COVERAGE_V10_DEFINITION.parent
        definition["federated_index"]["path"] = str(
            (definition_root / definition["federated_index"]["path"]).resolve()
        )
        for child in definition["children"]:
            child["release_path"] = str(
                (definition_root / child["release_path"]).resolve()
            )
        return definition

    def test_frozen_successor_reproduces_twice_offline_with_exact_v13_delta(
        self,
    ) -> None:
        self.assertEqual(
            hashlib.sha256(PUBLIC_COVERAGE_V9_DEFINITION.read_bytes()).hexdigest(),
            PUBLIC_COVERAGE_V9_DEFINITION_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(
                (PUBLIC_COVERAGE_V9 / "manifest.json").read_bytes()
            ).hexdigest(),
            PUBLIC_COVERAGE_V9_MANIFEST_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(PUBLIC_COVERAGE_V10_DEFINITION.read_bytes()).hexdigest(),
            PUBLIC_COVERAGE_V10_DEFINITION_SHA256,
        )

        with patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline build attempted network access"),
        ), patch.object(
            socket,
            "create_connection",
            side_effect=AssertionError("offline build attempted network access"),
        ):
            first_bundle = build_coverage_audit(PUBLIC_COVERAGE_V10_DEFINITION)
            second_bundle = build_coverage_audit(PUBLIC_COVERAGE_V10_DEFINITION)
            sealed = validate_coverage_audit(PUBLIC_COVERAGE_V10)
        self.assertEqual(first_bundle, second_bundle)
        self.assertEqual(first_bundle.audit, sealed)
        self.assertEqual(
            set(first_bundle.payloads),
            {path.name for path in PUBLIC_COVERAGE_V10.iterdir()},
        )
        for filename, raw in first_bundle.payloads.items():
            self.assertEqual(raw, (PUBLIC_COVERAGE_V10 / filename).read_bytes())
        self.assertEqual(
            hashlib.sha256(
                (PUBLIC_COVERAGE_V10 / "manifest.json").read_bytes()
            ).hexdigest(),
            PUBLIC_COVERAGE_V10_MANIFEST_SHA256,
        )
        self.assertEqual(
            first_bundle.manifest["artifacts"], PUBLIC_COVERAGE_V10_ARTIFACTS
        )
        self.assertEqual(
            first_bundle.audit["inputs"]["federated_index"]["manifest"]["sha256"],
            PUBLIC_FEDERATION_V9_MANIFEST_SHA256,
        )
        self.assertEqual(
            first_bundle.audit["inputs"]["federated_index"]["index"]["sha256"],
            PUBLIC_FEDERATION_V9_INDEX_SHA256,
        )

        previous = json.loads(
            (PUBLIC_COVERAGE_V9 / AUDIT_FILENAME).read_text(encoding="utf-8")
        )
        previous_gaps = json.loads(
            (PUBLIC_COVERAGE_V9 / GAP_REGISTRY_FILENAME).read_text(encoding="utf-8")
        )
        current = first_bundle.audit
        current_gaps = first_bundle.gaps
        previous_definition = json.loads(
            PUBLIC_COVERAGE_V9_DEFINITION.read_text(encoding="utf-8")
        )
        current_definition = json.loads(
            PUBLIC_COVERAGE_V10_DEFINITION.read_text(encoding="utf-8")
        )

        self.assertEqual(
            current_definition["public_benchmark"],
            previous_definition["public_benchmark"],
        )
        self.assertEqual(
            current_definition["federated_index"],
            {
                "expected_manifest_sha256": PUBLIC_FEDERATION_V9_MANIFEST_SHA256,
                "path": "../federated_indexes/2026-07-19-public-open-v9",
            },
        )
        previous_children = {
            child["release_id"]: child for child in previous_definition["children"]
        }
        current_children = {
            child["release_id"]: child for child in current_definition["children"]
        }
        self.assertEqual(
            set(current_children),
            (set(previous_children) - {self.OLD_OPEN_RELEASE_ID})
            | {self.NEW_OPEN_RELEASE_ID},
        )
        self.assertNotIn(self.OLD_OPEN_RELEASE_ID, current_children)
        for release_id in ("global-open-v3", "osm-fuzzy-review-v2"):
            self.assertEqual(current_children[release_id], previous_children[release_id])
        self.assertEqual(
            current_children[self.NEW_OPEN_RELEASE_ID]["expected_manifest_sha256"],
            OPEN_SEED_V20_MANIFEST_SHA256,
        )

        previous_methodology = previous_definition[
            "methodology_evidence_classification"
        ]
        current_methodology = self.normalize_open_release_id(
            current_definition["methodology_evidence_classification"]
        )
        assert isinstance(current_methodology, dict)
        current_permits = list(current_methodology["permits"])
        wisconsin = next(
            reference
            for reference in current_permits
            if reference["evidence_id"]
            == "928bbcd8-079d-5b85-a631-2477c6513a79"
        )
        self.assertEqual(
            wisconsin,
            {
                "evidence_id": "928bbcd8-079d-5b85-a631-2477c6513a79",
                "release_id": self.OLD_OPEN_RELEASE_ID,
            },
        )
        current_permits.remove(wisconsin)
        self.assertEqual(
            {**current_methodology, "permits": current_permits},
            previous_methodology,
        )

        expected_total_deltas = {
            "advisory_resolution_candidate_records": 0,
            "non_review_source_scoped_entity_records": 88,
            "review_only_source_scoped_entity_records": 0,
            "source_scoped_entity_records": 88,
        }
        for field, delta in expected_total_deltas.items():
            self.assertEqual(current["totals"][field] - previous["totals"][field], delta)
        self.assertEqual(current["totals"]["source_scoped_entity_records"], 15_707)
        self.assertEqual(
            current["totals"]["non_review_source_scoped_entity_records"], 9_577
        )
        self.assertEqual(
            current["totals"]["review_only_source_scoped_entity_records"], 6_130
        )
        self.assertEqual(
            current["totals"]["advisory_resolution_candidate_records"], 100_409
        )

        field_delta = {
            field: current["totals"]["field_totals"][field]
            - previous["totals"]["field_totals"][field]
            for field in (
                "capacity_entity_rows",
                "capacity_observations",
                "complete_lifecycle_claim_rows",
                "construction_evidence_observations",
                "coordinate_rows",
                "country_rows",
                "informative_lifecycle_status_rows",
                "lifecycle_status_rows",
                "non_review_under_construction_rows",
                "operating_model_rows",
                "pipeline_rows",
                "source_scoped_rows",
                "status_as_of_rows",
                "status_evidence_rows",
                "under_construction_rows",
                "unresolved_lifecycle_status_rows",
                "workload_rows",
            )
        }
        self.assertEqual(
            field_delta,
            {
                "capacity_entity_rows": 30,
                "capacity_observations": 30,
                "complete_lifecycle_claim_rows": 46,
                "construction_evidence_observations": 25,
                "coordinate_rows": 0,
                "country_rows": 88,
                "informative_lifecycle_status_rows": 46,
                "lifecycle_status_rows": 46,
                "non_review_under_construction_rows": 27,
                "operating_model_rows": 1,
                "pipeline_rows": 28,
                "source_scoped_rows": 88,
                "status_as_of_rows": 46,
                "status_evidence_rows": 46,
                "under_construction_rows": 27,
                "unresolved_lifecycle_status_rows": 42,
                "workload_rows": 5,
            },
        )
        expected_counter_deltas = {
            "capacity_metric_counts": {
                "critical_it_mw": 27,
                "generation_nameplate_mw": 1,
                "grid_connection_mw": 2,
            },
            "capacity_stage_counts": {"contracted": 2, "planned": 28},
            "non_review_source_declared_entity_kind_counts": {
                "campus": 42,
                "project": 46,
            },
            "status_counts": {
                "__MISSING__": 42,
                "announced": 1,
                "mep_electrical": 12,
                "shell": 3,
                "site_preparation": 3,
                "under_construction": 27,
            },
            "workload_counts": {"ai_specialized_unspecified": 5},
        }
        for field, expected in expected_counter_deltas.items():
            old_counts = Counter(previous["totals"]["field_totals"][field])
            new_counts = Counter(current["totals"]["field_totals"][field])
            self.assertEqual(dict(new_counts - old_counts), expected)

        previous_groups = {
            self.group_key(group): group for group in previous["groups"]
        }
        current_groups = {self.group_key(group): group for group in current["groups"]}
        self.assertEqual(len(previous_groups), 320)
        self.assertEqual(len(current_groups), 372)
        self.assertLessEqual(previous_groups.keys(), current_groups.keys())
        added_group_keys = current_groups.keys() - previous_groups.keys()
        self.assertEqual(
            Counter(key[1] for key in added_group_keys),
            {"release_source": 23, "release_source_country": 29},
        )
        for key, group in previous_groups.items():
            if key[0] != self.OLD_OPEN_RELEASE_ID:
                self.assertEqual(current_groups[key], group)

        previous_gap_rows = {
            self.gap_key(gap): gap for gap in previous_gaps["gaps"]
        }
        current_gap_rows = {
            self.gap_key(gap): gap for gap in current_gaps["gaps"]
        }
        self.assertEqual(
            previous_gap_rows.keys() - current_gap_rows.keys(),
            {
                (
                    "release_source",
                    self.OLD_OPEN_RELEASE_ID,
                    "digital_realty_press_releases",
                    None,
                    "source_scoped_rows",
                )
            },
        )
        self.assertEqual(len(current_gap_rows) - len(previous_gap_rows), 244)
        self.assertEqual(len(current_gap_rows.keys() - previous_gap_rows.keys()), 245)
        for key in previous_gap_rows.keys() & current_gap_rows.keys():
            if key[1] != self.OLD_OPEN_RELEASE_ID:
                self.assertEqual(
                    self.normalized_gap(current_gap_rows[key]),
                    self.normalized_gap(previous_gap_rows[key]),
                )
        self.assertEqual(
            current_gaps["summary"],
            {
                "open_gaps": 2_063,
                "by_severity": {
                    "high": 84,
                    "info": 12,
                    "low": 1_235,
                    "medium": 732,
                },
                "by_field": {
                    "annual_energy": 294,
                    "capacity": 284,
                    "coordinates": 74,
                    "country": 3,
                    "country_iso_a2": 5,
                    "informative_lifecycle_status": 283,
                    "licensed_row_level_benchmark": 1,
                    "lifecycle_status": 113,
                    "operating_model": 301,
                    "parity": 1,
                    "semianalysis_public_capacity_outputs": 1,
                    "semianalysis_public_construction_timeline_pjm": 1,
                    "semianalysis_public_evidence_methodology": 1,
                    "semianalysis_public_facility_scope_count": 1,
                    "semianalysis_public_temporal_granularity": 1,
                    "source_scoped_rows": 12,
                    "status_as_of": 113,
                    "status_evidence": 113,
                    "status_stale_366_plus_days": 167,
                    "unique_physical_sites": 1,
                    "workload": 293,
                },
            },
        )
        previous_field_counts = Counter(
            gap["field"] for gap in previous_gaps["gaps"]
        )
        current_field_counts = Counter(gap["field"] for gap in current_gaps["gaps"])
        self.assertEqual(
            {
                field: current_field_counts[field] - previous_field_counts[field]
                for field in current_field_counts.keys() | previous_field_counts.keys()
                if current_field_counts[field] != previous_field_counts[field]
            },
            {
                "annual_energy": 29,
                "capacity": 27,
                "coordinates": 30,
                "informative_lifecycle_status": 24,
                "lifecycle_status": 24,
                "operating_model": 29,
                "source_scoped_rows": 3,
                "status_as_of": 24,
                "status_evidence": 24,
                "status_stale_366_plus_days": 2,
                "workload": 28,
            },
        )
        previous_severity_counts = Counter(
            gap["severity"] for gap in previous_gaps["gaps"]
        )
        current_severity_counts = Counter(
            gap["severity"] for gap in current_gaps["gaps"]
        )
        self.assertEqual(
            {
                severity: current_severity_counts[severity]
                - previous_severity_counts[severity]
                for severity in current_severity_counts.keys()
                | previous_severity_counts.keys()
                if current_severity_counts[severity]
                != previous_severity_counts[severity]
            },
            {"high": 30, "info": 3, "low": 113, "medium": 98},
        )

        comparison = current["semianalysis_public_comparison"]
        previous_comparison = previous["semianalysis_public_comparison"]
        self.assertEqual(comparison["benchmark"], previous_comparison["benchmark"])
        self.assertEqual(
            comparison["licensed_row_level_benchmark"],
            previous_comparison["licensed_row_level_benchmark"],
        )
        self.assertEqual(
            comparison["overall_parity"], previous_comparison["overall_parity"]
        )
        self.assertEqual(comparison["overall_parity"]["status"], "pending")
        self.assertEqual(
            comparison["licensed_row_level_benchmark"]["status"], "pending"
        )
        self.assertTrue(
            all(item["parity_status"] == "pending" for item in comparison["comparisons"])
        )
        methodology = next(
            item
            for item in comparison["comparisons"]
            if item["claim_id"] == "evidence_methodology"
        )["atlas_evidence"]
        self.assertEqual(methodology["permits"]["evidence_reference_count"], 5)
        self.assertEqual(
            methodology["permits"]["source_families"],
            [
                "environment_agency_permit_application_supporting_document",
                "indiana_idem_air_permit",
                "north_carolina_deq_air_permit_public_notice",
                "north_dakota_deq_air_quality_records",
                "wisconsin_dnr_environmental_review_pages",
            ],
        )
        self.assertIn(
            {
                "evidence_id": "928bbcd8-079d-5b85-a631-2477c6513a79",
                "release_id": self.NEW_OPEN_RELEASE_ID,
                "source_family": "wisconsin_dnr_environmental_review_pages",
            },
            methodology["permits"]["evidence_references"],
        )
        self.assertEqual(methodology["power_data"]["capacity_observation_count"], 1_178)
        self.assertEqual(
            methodology["power_data"][
                "capacity_observations_with_resolved_evidence"
            ],
            1_178,
        )

        self.assertEqual(current["scope"], previous["scope"])
        self.assertFalse(current["scope"]["children_merged"])
        self.assertFalse(current["scope"]["cross_source_deduplication"])
        self.assertFalse(current["scope"]["review_candidates_promoted"])
        self.assertFalse(current["scope"]["candidate_rows_counted_as_facilities"])
        self.assertIsNone(current["scope"]["confirmed_duplicate_relationships"])
        self.assertIsNone(current["scope"]["unique_physical_sites"])
        unique_site_gap = next(
            gap
            for gap in current_gaps["gaps"]
            if gap["field"] == "unique_physical_sites"
        )
        self.assertEqual(unique_site_gap["severity"], "high")

        self.assertFalse(PUBLIC_COVERAGE_V10_DEFINITION.is_symlink())
        self.assertEqual(
            stat.S_IMODE(PUBLIC_COVERAGE_V10_DEFINITION.stat().st_mode), 0o644
        )
        self.require_frozen_modes(PUBLIC_COVERAGE_V9)
        self.require_frozen_modes(PUBLIC_COVERAGE_V10)

    def test_successor_fails_closed_on_wrong_pins_symlink_and_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for case in ("federation", "child"):
                with self.subTest(case=case):
                    definition = self.absolute_definition()
                    if case == "federation":
                        definition["federated_index"][
                            "expected_manifest_sha256"
                        ] = "0" * 64
                        pattern = "federated index manifest SHA-256"
                    else:
                        open_child = next(
                            child
                            for child in definition["children"]
                            if child["release_id"] == self.NEW_OPEN_RELEASE_ID
                        )
                        open_child["expected_manifest_sha256"] = "0" * 64
                        pattern = "manifest SHA-256 does not match audit definition"
                    path = root / f"wrong-{case}.json"
                    path.write_bytes(_json_bytes(definition))
                    with self.assertRaisesRegex(CoverageAuditError, pattern):
                        build_coverage_audit(path)

            symlink_copy = root / "symlink-copy"
            shutil.copytree(PUBLIC_COVERAGE_V10, symlink_copy)
            symlink_copy.chmod(0o755)
            report = symlink_copy / "REPORT.md"
            report.chmod(0o644)
            report.unlink()
            report.symlink_to(PUBLIC_COVERAGE_V10 / "REPORT.md")
            with self.assertRaisesRegex(CoverageAuditError, "regular file"):
                validate_coverage_audit(symlink_copy)

            mode_copy = root / "mode-copy"
            shutil.copytree(PUBLIC_COVERAGE_V10, mode_copy)
            mode_copy.chmod(0o755)
            with self.assertRaisesRegex(CoverageAuditError, "mode must be 0555"):
                self.require_frozen_modes(mode_copy)


if __name__ == "__main__":
    unittest.main()
