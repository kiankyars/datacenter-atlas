from __future__ import annotations

import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from datacenter_atlas.cross_release import (
    CrossReleaseResolutionError,
    _release_input,
    build_cross_release_resolution,
    validate_cross_release_resolution,
)
from datacenter_atlas.database import initialize
from datacenter_atlas.global_snapshot import _add_manifest_file
from datacenter_atlas.models import Evidence, EvidenceKind, Facility
from datacenter_atlas.release import write_release
from datacenter_atlas.repository import add_evidence, add_facility, add_snapshot


AS_OF = "2026-07-18"
RECORDED_AT = "2026-07-18T20:00:00Z"


def _write_release(
    directory: Path,
    *,
    entity_id: str,
    source_family: str,
    upstream_source_family: str | None,
    name: str,
    latitude: float,
    longitude: float,
) -> Path:
    directory.mkdir()
    connection, _ = initialize(directory / "atlas.sqlite")
    evidence_id = f"evidence:{entity_id}"
    metadata = (
        {"upstream_source_family": upstream_source_family}
        if upstream_source_family
        else None
    )
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
        metadata=metadata,
    )
    add_facility(
        connection,
        Facility(entity_id, f"{source_family}:{entity_id}", evidence_id),
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
        tags={"country": "FR", "operator": "Digital Realty"},
        evidence_id=evidence_id,
        as_of_date=AS_OF,
        recorded_at=RECORDED_AT,
        method="test",
        confidence=0.9,
    )
    connection.commit()
    write_release(
        connection,
        directory,
        as_of=AS_OF,
        recorded_at=RECORDED_AT,
    )
    connection.close()
    _add_manifest_file(directory, "atlas.sqlite")
    return directory


class CrossReleaseResolutionTests(unittest.TestCase):
    def fixture(self, root: Path) -> tuple[Path, Path]:
        left = _write_release(
            root / "scrutica",
            entity_id="scrutica-mrs1",
            source_family="scrutica",
            upstream_source_family="openstreetmap",
            name="Digital Realty MRS1",
            latitude=43.3110164,
            longitude=5.3739134,
        )
        right = _write_release(
            root / "global-open",
            entity_id="open-mrs1",
            source_family="openstreetmap",
            upstream_source_family=None,
            name="Digital Realty MRS1",
            latitude=43.31101645,
            longitude=5.37391345,
        )
        return left, right

    def test_builds_atomic_read_only_candidate_crosswalk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left, right = self.fixture(root)
            children_before = {
                path: path.read_bytes()
                for child in (left, right)
                for path in child.iterdir()
            }
            output = root / "crosswalk"

            manifest = build_cross_release_resolution(
                left,
                right,
                output,
                left_label="scrutica-2026-07-18",
                right_label="global-open-v3",
                generated_at="2026-07-18T22:00:00Z",
            )

            self.assertEqual(validate_cross_release_resolution(output), manifest)
            self.assertEqual(manifest["counts"]["candidate_links"], 1)
            self.assertEqual(
                manifest["counts"]["candidate_links_by_relationship_suggestion"],
                {"same_site_candidate": 1},
            )
            self.assertEqual(
                manifest["counts"]["candidate_links_by_source_independence"],
                {"shared_root": 1},
            )
            self.assertEqual(
                manifest["counts"][
                    "candidate_links_by_relationship_and_source_independence"
                ],
                {"same_site_candidate | shared_root": 1},
            )
            self.assertEqual(
                manifest["counts"]["exact_upstream_identity_candidate_links"], 0
            )
            self.assertEqual(
                manifest["counts"]["same_site_or_part_of_candidate_links"], 1
            )
            self.assertIsNone(manifest["counts"]["unique_physical_sites"])
            self.assertTrue(
                manifest["scope"]["selected_child_fields_reproduced_in_candidate_rows"]
            )
            self.assertFalse(manifest["scope"]["child_databases_copied"])
            candidate = json.loads(
                (output / "resolution_candidates.json").read_text(encoding="utf-8")
            )[0]
            self.assertEqual(
                (candidate["left_entity_id"], candidate["right_entity_id"]),
                ("scrutica-mrs1", "open-mrs1"),
            )
            self.assertFalse(candidate["signals"]["source_independent"])
            self.assertEqual(
                children_before,
                {
                    path: path.read_bytes()
                    for child in (left, right)
                    for path in child.iterdir()
                },
            )

    def test_child_manifest_rejects_equivalent_noncanonical_offset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left, _right = self.fixture(root)
            manifest_path = left / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["recorded_at"] = "2026-07-18T21:00:00+01:00"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False)
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                CrossReleaseResolutionError,
                "canonical UTC whole seconds",
            ):
                _release_input(left, "left")

    def test_validator_rejects_tampering_and_builder_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left, right = self.fixture(root)
            output = root / "crosswalk"
            build_cross_release_resolution(
                left,
                right,
                output,
                left_label="left",
                right_label="right",
                generated_at="2026-07-18T22:00:00Z",
            )
            with self.assertRaisesRegex(
                CrossReleaseResolutionError, "existing output directory"
            ):
                build_cross_release_resolution(
                    left,
                    right,
                    output,
                    left_label="left",
                    right_label="right",
                    generated_at="2026-07-18T22:00:00Z",
                )
            (output / "summary.json").write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                CrossReleaseResolutionError, "checkpoint does not match"
            ):
                validate_cross_release_resolution(output)

    def test_validator_rejects_hash_consistent_csv_json_divergence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left, right = self.fixture(root)
            output = root / "crosswalk"
            build_cross_release_resolution(
                left,
                right,
                output,
                left_label="left",
                right_label="right",
                generated_at="2026-07-18T22:00:00Z",
            )

            csv_path = output / "resolution_candidates.csv"
            rows = list(
                csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8")))
            )
            rows[0]["score"] = "not-a-score"
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(
                stream, fieldnames=rows[0].keys(), lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
            csv_raw = stream.getvalue().encode("utf-8")
            csv_path.write_bytes(csv_raw)

            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"][csv_path.name] = {
                "bytes": len(csv_raw),
                "sha256": hashlib.sha256(csv_raw).hexdigest(),
            }
            manifest_raw = (
                json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            ).encode("utf-8")
            manifest_path.write_bytes(manifest_raw)
            (output / "manifest.sha256").write_text(
                f"{hashlib.sha256(manifest_raw).hexdigest()}  manifest.json\n",
                encoding="ascii",
            )

            with self.assertRaisesRegex(
                CrossReleaseResolutionError, "CSV and JSON rows differ"
            ):
                validate_cross_release_resolution(output)

    def test_validator_rejects_hash_consistent_invalid_candidate_score(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left, right = self.fixture(root)
            output = root / "crosswalk"
            build_cross_release_resolution(
                left,
                right,
                output,
                left_label="left",
                right_label="right",
                generated_at="2026-07-18T22:00:00Z",
            )

            json_path = output / "resolution_candidates.json"
            candidates = json.loads(json_path.read_text(encoding="utf-8"))
            candidates[0]["score"] = 0.0
            json_raw = (
                json.dumps(candidates, indent=2, sort_keys=True, ensure_ascii=False)
                + "\n"
            ).encode("utf-8")
            json_path.write_bytes(json_raw)

            csv_path = output / "resolution_candidates.csv"
            rows = list(
                csv.DictReader(io.StringIO(csv_path.read_text(encoding="utf-8")))
            )
            rows[0]["score"] = "0.0"
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(
                stream, fieldnames=rows[0].keys(), lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
            csv_raw = stream.getvalue().encode("utf-8")
            csv_path.write_bytes(csv_raw)

            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for path, raw in ((json_path, json_raw), (csv_path, csv_raw)):
                manifest["files"][path.name] = {
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            manifest_raw = (
                json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False)
                + "\n"
            ).encode("utf-8")
            manifest_path.write_bytes(manifest_raw)
            (output / "manifest.sha256").write_text(
                f"{hashlib.sha256(manifest_raw).hexdigest()}  manifest.json\n",
                encoding="ascii",
            )

            with self.assertRaisesRegex(
                CrossReleaseResolutionError, "score does not reconcile"
            ):
                validate_cross_release_resolution(output)

    def test_builder_revalidates_children_after_querying(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left, right = self.fixture(root)
            output = root / "crosswalk"
            original_validator = validate_cross_release_resolution

            def validate_then_drift(path: Path) -> dict:
                result = original_validator(path)
                with (left / "ATTRIBUTION.txt").open("ab") as stream:
                    stream.write(b"drift")
                return result

            with patch(
                "datacenter_atlas.cross_release.validate_cross_release_resolution",
                side_effect=validate_then_drift,
            ), self.assertRaisesRegex(
                CrossReleaseResolutionError, "left release validation failed"
            ):
                build_cross_release_resolution(
                    left,
                    right,
                    output,
                    left_label="left",
                    right_label="right",
                    generated_at="2026-07-18T22:00:00Z",
                )
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".crosswalk.stage-*")), [])


if __name__ == "__main__":
    unittest.main()
