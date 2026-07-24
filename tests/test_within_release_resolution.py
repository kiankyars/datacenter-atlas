from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from datacenter_atlas.database import initialize
from datacenter_atlas.models import Campus, Evidence, EvidenceKind, Facility
from datacenter_atlas.release import write_release
from datacenter_atlas.repository import (
    add_campus,
    add_evidence,
    add_facility,
    add_snapshot,
)
from datacenter_atlas.within_release_resolution import (
    DEFINITION_FORMAT,
    WithinReleaseResolutionError,
    _inspect_release,
    validate_within_release_resolution,
    write_within_release_resolution,
)


AS_OF = "2026-07-18"
RECORDED_AT = "2026-07-18T20:00:00Z"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _add_entity(
    connection,
    *,
    entity_id: str,
    kind: str,
    stable_key: str,
    source_family: str,
    name: str,
    latitude: float,
    longitude: float,
    tags: dict[str, str],
) -> None:
    evidence_id = f"evidence:{entity_id}"
    add_evidence(
        connection,
        Evidence(
            id=evidence_id,
            kind=EvidenceKind.THIRD_PARTY_DATASET,
            title=f"Evidence for {name}",
            source_url=f"https://example.test/{entity_id}",
            retrieved_at=RECORDED_AT,
            publisher=source_family,
            source_family=source_family,
            license="test-license",
            attribution=f"Attribution for {source_family}",
        ),
    )
    if kind == "campus":
        add_campus(
            connection,
            Campus(entity_id, stable_key, evidence_id),
            created_at=RECORDED_AT,
        )
    else:
        add_facility(
            connection,
            Facility(entity_id, stable_key, evidence_id),
            created_at=RECORDED_AT,
        )
    add_snapshot(
        connection,
        snapshot_id=f"snapshot:{entity_id}",
        entity_id=entity_id,
        name=name,
        latitude=latitude,
        longitude=longitude,
        geometry=None,
        tags=tags,
        evidence_id=evidence_id,
        as_of_date=AS_OF,
        recorded_at=RECORDED_AT,
        method="test",
        confidence=0.9,
    )


def _write_release(directory: Path, *, review_only: bool = False) -> Path:
    directory.mkdir()
    connection, _ = initialize(directory.parent / f"{directory.name}.sqlite")
    if review_only:
        _add_entity(
            connection,
            entity_id=f"{directory.name}-review",
            kind="facility",
            stable_key="osm:way/999",
            source_family="openstreetmap:fuzzy_discovery",
            name="Unverified structural lead",
            latitude=48.0,
            longitude=2.0,
            tags={"country": "FR"},
        )
    else:
        _add_entity(
            connection,
            entity_id="a-osm-object",
            kind="facility",
            stable_key="osm:way/123",
            source_family="openstreetmap",
            name="Atlas DC",
            latitude=48.00000,
            longitude=2.00000,
            tags={"country": "FR", "operator": "Example Cloud"},
        )
        _add_entity(
            connection,
            entity_id="b-osm-container",
            kind="facility",
            stable_key="osm:way/123:facility-container",
            source_family="openstreetmap",
            name="Atlas DC facility container",
            latitude=48.00000,
            longitude=2.00000,
            tags={"country": "FR", "operator": "Example Cloud"},
        )
        _add_entity(
            connection,
            entity_id="c-wikidata",
            kind="facility",
            stable_key="wikidata:Q123",
            source_family="wikidata",
            name="Atlas DC",
            latitude=48.00003,
            longitude=2.00003,
            tags={"country": "FR", "operator": "Example Cloud"},
        )
        _add_entity(
            connection,
            entity_id="d-campus",
            kind="campus",
            stable_key="epoch-ai:data-center:test-campus",
            source_family="epoch_ai_data_centers",
            name="Atlas Campus",
            latitude=48.00006,
            longitude=2.00006,
            tags={"country": "FR", "owner": "Example Cloud"},
        )
    connection.commit()
    write_release(
        connection,
        directory,
        as_of=AS_OF,
        recorded_at=RECORDED_AT,
    )
    connection.close()
    if review_only:
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["review_only"] = True
        manifest_path.write_bytes(_canonical(manifest))
    return directory


def _definition(path: Path, releases: list[tuple[str, Path, bool]]) -> Path:
    children = []
    for release_id, release_path, review_only in sorted(releases):
        manifest_raw = (release_path / "manifest.json").read_bytes()
        children.append(
            {
                "release_id": release_id,
                "release_path": release_path.name,
                "expected_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                "expected_review_only": review_only,
            }
        )
    document = {
        "schema_version": 1,
        "format": DEFINITION_FORMAT,
        "bundle_id": "test-within-release-v1",
        "generated_at": "2026-07-18T21:00:00Z",
        "review_only_policy": "exclude",
        "thresholds": {
            "spatial_max_distance_m": 1000.0,
            "same_site_max_distance_m": 250.0,
            "part_of_max_distance_m": 750.0,
            "same_site_min_score": 0.62,
            "part_of_min_score": 0.55,
            "semantic_min_similarity": 0.82,
        },
        "releases": children,
        "federation": None,
    }
    path.write_bytes(_canonical(document))
    return path


class WithinReleaseResolutionTests(unittest.TestCase):
    def test_child_manifest_rejects_equivalent_noncanonical_offset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = _write_release(root / "open")
            manifest_path = release / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["recorded_at"] = "2026-07-18T21:00:00+01:00"
            manifest_raw = _canonical(manifest)
            manifest_path.write_bytes(manifest_raw)
            definition = {
                "release_id": "open",
                "release_path": release,
                "expected_manifest_sha256": hashlib.sha256(
                    manifest_raw
                ).hexdigest(),
                "expected_review_only": False,
            }
            with self.assertRaisesRegex(
                WithinReleaseResolutionError,
                "canonical UTC whole seconds",
            ):
                _inspect_release(definition)

    def test_builds_all_narrow_candidate_classes_without_mutating_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = _write_release(root / "open-release")
            before = {path.name: path.read_bytes() for path in release.iterdir()}
            definition = _definition(
                root / "definition.json", [("open-release", release, False)]
            )
            output = root / "resolution"

            manifest = write_within_release_resolution(definition, output)

            self.assertEqual(
                validate_within_release_resolution(
                    output, definition_path=definition, verify_inputs=True
                ),
                manifest,
            )
            candidates = json.loads(
                (output / "resolution-candidates.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                {row["candidate_class"] for row in candidates},
                {"shared_source_identity", "tight_same_site", "part_of"},
            )
            exact = next(
                row
                for row in candidates
                if row["candidate_class"] == "shared_source_identity"
            )
            self.assertIn(
                "openstreetmap:way/123",
                exact["signals"]["matching_typed_source_identities"],
            )
            self.assertTrue(exact["signals"]["source_generated_structure"])
            self.assertFalse(exact["signals"]["source_independent"])
            self.assertTrue(all(row["advisory_only"] for row in candidates))
            self.assertTrue(
                all(row["automatic_merge_allowed"] is False for row in candidates)
            )
            self.assertNotIn(
                "nearby_only",
                manifest["counts"]["candidate_links_by_relationship_suggestion"],
            )
            self.assertIsNone(manifest["counts"]["unique_physical_sites"])
            self.assertEqual(
                before,
                {path.name: path.read_bytes() for path in release.iterdir()},
            )

    def test_excludes_review_only_release_before_scanning(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = _write_release(root / "open-release")
            review = _write_release(root / "review-release", review_only=True)
            definition = _definition(
                root / "definition.json",
                [
                    ("open-release", release, False),
                    ("review-release", review, True),
                ],
            )
            output = root / "resolution"

            manifest = write_within_release_resolution(definition, output)

            counts = manifest["counts"]
            self.assertEqual(counts["excluded_review_only_release_bundles"], 1)
            self.assertEqual(
                counts["excluded_review_only_release_ids"], ["review-release"]
            )
            self.assertEqual(
                counts["review_only_source_scoped_entity_records_excluded"], 1
            )
            self.assertEqual(
                {row["release_id"] for row in json.loads(
                    (output / "resolution-candidates.json").read_text(encoding="utf-8")
                )},
                {"open-release"},
            )

    def test_validator_rejects_hash_consistent_semantic_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = _write_release(root / "open-release")
            definition = _definition(
                root / "definition.json", [("open-release", release, False)]
            )
            output = root / "resolution"
            write_within_release_resolution(definition, output)

            candidates_path = output / "resolution-candidates.json"
            candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates[0]["automatic_merge_allowed"] = True
            raw = _canonical(candidates)
            candidates_path.write_bytes(raw)
            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"][candidates_path.name] = {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
            manifest_raw = _canonical(manifest)
            manifest_path.write_bytes(manifest_raw)
            (output / "manifest.sha256").write_text(
                f"{hashlib.sha256(manifest_raw).hexdigest()}  manifest.json\n",
                encoding="ascii",
            )

            with self.assertRaisesRegex(
                WithinReleaseResolutionError, "review scope is invalid"
            ):
                validate_within_release_resolution(output)

    def test_definition_must_exclude_review_only_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release = _write_release(root / "open-release")
            definition = _definition(
                root / "definition.json", [("open-release", release, False)]
            )
            document = json.loads(definition.read_text(encoding="utf-8"))
            document["review_only_policy"] = "include"
            definition.write_bytes(_canonical(document))
            with self.assertRaisesRegex(
                WithinReleaseResolutionError, "review-only inputs must be excluded"
            ):
                write_within_release_resolution(definition, root / "resolution")


if __name__ == "__main__":
    unittest.main()
