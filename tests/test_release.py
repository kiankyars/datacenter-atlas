from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.osm import OpenStreetMapAdapter
from datacenter_atlas.release import write_release


class ReleaseTests(unittest.TestCase):
    def test_release_is_auditable_and_hashes_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            connection, _ = initialize(root / "atlas.sqlite")
            try:
                OpenStreetMapAdapter().import_file(
                    connection,
                    Path(__file__).parent / "fixtures" / "osm_minimal.json",
                    retrieved_at="2026-07-17T12:00:00Z",
                )
                result = write_release(
                    connection,
                    root / "release",
                    as_of="2026-07-17",
                    recorded_at="2026-07-17T13:00:00Z",
                )
            finally:
                connection.close()

            release = root / "release"
            expected = {
                "atlas.geojson",
                "entities.csv",
                "capacity_estimates.csv",
                "construction_pipeline.csv",
                "construction_source_signals.csv",
                "evidence.csv",
                "summary.json",
                "source_inputs.json",
                "resolution_candidates.csv",
                "resolution_candidates.json",
                "README.md",
                "ATTRIBUTION.txt",
                "manifest.json",
            }
            self.assertEqual({path.name for path in release.iterdir()}, expected)
            manifest = json.loads((release / "manifest.json").read_text())
            self.assertEqual(manifest["entities"], result["entities"])
            for name, facts in manifest["files"].items():
                raw = (release / name).read_bytes()
                self.assertEqual(facts["bytes"], len(raw))
                self.assertEqual(facts["sha256"], hashlib.sha256(raw).hexdigest())

            with (release / "entities.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertTrue(rows)
            self.assertTrue(all(row["snapshot_evidence_id"] for row in rows))
            with (release / "construction_pipeline.csv").open(newline="") as stream:
                construction_rows = list(csv.DictReader(stream))
            with (release / "construction_source_signals.csv").open(
                newline=""
            ) as stream:
                construction_signals = list(csv.DictReader(stream))
            with (release / "evidence.csv").open(newline="") as stream:
                evidence_by_id = {
                    row["evidence_id"]: row for row in csv.DictReader(stream)
                }
            grouped: dict[str, list[dict[str, str]]] = {}
            for row in construction_rows:
                grouped.setdefault(row["status_evidence_id"], []).append(row)
            self.assertEqual(len(construction_signals), len(grouped))
            self.assertEqual(
                manifest["construction_pipeline_records"], len(construction_rows)
            )
            self.assertEqual(
                manifest["construction_source_signals"], len(construction_signals)
            )
            summary = json.loads((release / "summary.json").read_text())
            self.assertEqual(
                summary["construction_pipeline_records"], len(construction_rows)
            )
            self.assertEqual(
                summary["construction_source_signals"], len(construction_signals)
            )
            for signal in construction_signals:
                evidence_id = signal["source_observation_evidence_id"]
                expected_entities = {
                    (row["entity_id"], row["entity_kind"], row["stable_key"])
                    for row in grouped[evidence_id]
                }
                affected = json.loads(signal["affected_entities_json"])
                self.assertEqual(
                    {
                        (row["entity_id"], row["entity_kind"], row["stable_key"])
                        for row in affected
                    },
                    expected_entities,
                )
                self.assertEqual(
                    int(signal["affected_entity_count"]), len(expected_entities)
                )
                self.assertIn(
                    signal["representative_entity_id"],
                    {entity_id for entity_id, _, _ in expected_entities},
                )
                if any(kind != "project" for _, kind, _ in expected_entities):
                    self.assertNotEqual(
                        signal["representative_entity_kind"], "project"
                    )
                source = evidence_by_id[evidence_id]
                self.assertEqual(signal["source_kind"], source["kind"])
                self.assertEqual(signal["source_family"], source["source_family"])
                self.assertEqual(signal["source_title"], source["title"])
                self.assertEqual(signal["source_url"], source["source_url"])
                self.assertEqual(
                    signal["source_content_hash"], source["content_hash"]
                )
            self.assertIn("© OpenStreetMap contributors", (release / "ATTRIBUTION.txt").read_text())
            readme = (release / "README.md").read_text()
            self.assertIn("not a global census", readme)
            self.assertIn("construction_source_signals.csv", readme)
            self.assertIn("not cross-source deduplication", readme)
            self.assertIn("not a count of unique physical sites", readme)

    def test_custom_readme_is_hashed_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            connection, _ = initialize(root / "atlas.sqlite")
            try:
                OpenStreetMapAdapter().import_file(
                    connection,
                    Path(__file__).parent / "fixtures" / "osm_minimal.json",
                    retrieved_at="2026-07-17T12:00:00Z",
                )
                custom_readme = "# Global open snapshot\n\nExact custom scope text.\n"
                write_release(
                    connection,
                    root / "release",
                    as_of="2026-07-17",
                    recorded_at="2026-07-17T13:00:00Z",
                    readme=custom_readme,
                )
            finally:
                connection.close()

            readme = (root / "release" / "README.md").read_text()
            manifest = json.loads((root / "release" / "manifest.json").read_text())
            raw = readme.encode("utf-8")
            self.assertEqual(readme, custom_readme)
            self.assertEqual(manifest["files"]["README.md"]["bytes"], len(raw))
            self.assertEqual(
                manifest["files"]["README.md"]["sha256"],
                hashlib.sha256(raw).hexdigest(),
            )

    def test_publication_contract_v2_covers_all_claim_attribution_and_methods(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            connection, _ = initialize(root / "atlas.sqlite")
            try:
                CuratedOfficialSourceAdapter().import_file(
                    connection,
                    Path(__file__).parents[1]
                    / "sources"
                    / "curated-official-2026-07-19-related-saline-stargate.json",
                    retrieved_at="2026-07-19T13:34:32Z",
                )
                result = write_release(
                    connection,
                    root / "release",
                    as_of="2026-07-19",
                    recorded_at="2026-07-19T13:55:00Z",
                    publication_contract_version=2,
                )
            finally:
                connection.close()

            release = root / "release"
            attribution = (release / "ATTRIBUTION.txt").read_text().splitlines()
            geojson = json.loads((release / "atlas.geojson").read_text())
            self.assertEqual(attribution, ["DTE Energy", "Related Digital"])
            self.assertEqual(geojson["attribution"], attribution)

            readme = (release / "README.md").read_text()
            self.assertNotIn("atlas.html", readme)
            self.assertIn("Capacity and energy semantics are row-specific", readme)
            self.assertIn("Annual-energy estimates are modeled, not metered", readme)
            self.assertIn("contracted grid load", readme)
            self.assertIn("Power generation", readme)
            self.assertEqual(result["format"], "datacenter-atlas-release-v1")

    def test_publication_contract_v3_keeps_user_tenant_and_customer_roles_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            connection, _ = initialize(root / "atlas.sqlite")
            try:
                inputs = (
                    (
                        "curated-official-2026-07-20-hyperco-dayone-koria-v2.json",
                        "2026-07-20T01:29:39Z",
                    ),
                    (
                        "curated-official-2026-07-20-cipher-black-pearl-phase-1-aws-retrofit.json",
                        "2026-07-20T01:40:05Z",
                    ),
                    (
                        "curated-official-2026-07-19-related-saline-stargate.json",
                        "2026-07-19T13:34:32Z",
                    ),
                )
                for filename, retrieved_at in inputs:
                    CuratedOfficialSourceAdapter().import_file(
                        connection,
                        Path(__file__).parents[1] / "sources" / filename,
                        retrieved_at=retrieved_at,
                    )
                write_release(
                    connection,
                    root / "legacy-v2",
                    as_of="2026-07-20",
                    recorded_at="2026-07-20T02:15:00Z",
                    publication_contract_version=2,
                )
                write_release(
                    connection,
                    root / "role-safe-v3",
                    as_of="2026-07-20",
                    recorded_at="2026-07-20T02:15:00Z",
                    publication_contract_version=3,
                )
            finally:
                connection.close()

            def release_rows(directory: str, filename: str) -> dict[str, dict[str, str]]:
                with (root / directory / filename).open(newline="", encoding="utf-8") as stream:
                    return {
                        row["stable_key"]: row for row in csv.DictReader(stream)
                    }

            legacy = release_rows("legacy-v2", "entities.csv")
            current = release_rows("role-safe-v3", "entities.csv")
            black_pearl = (
                "curated:cipher-digital-black-pearl-wink-texas-data-center-campus:"
                "aws-phase-1-retrofit"
            )
            koria = (
                "curated:hyperco-dayone-koria-unnamed-data-center-campus:current-build"
            )
            saline = (
                "curated:related-openai-oracle-stargate-michigan-saline:current-build"
            )

            self.assertNotIn("tenants", legacy[black_pearl])
            self.assertNotIn("customers", legacy[black_pearl])
            self.assertEqual(legacy[black_pearl]["users"], "Amazon Web Services, Inc.")
            self.assertEqual(legacy[saline]["users"], "OpenAI; Oracle")

            self.assertEqual(current[koria]["users"], "TikTok")
            self.assertEqual(current[koria]["tenants"], "")
            self.assertEqual(current[koria]["customers"], "")
            self.assertEqual(current[black_pearl]["users"], "")
            self.assertEqual(
                current[black_pearl]["tenants"], "Amazon Web Services, Inc."
            )
            self.assertEqual(current[black_pearl]["customers"], "")
            self.assertEqual(current[saline]["users"], "")
            self.assertEqual(current[saline]["tenants"], "")
            self.assertEqual(current[saline]["customers"], "OpenAI; Oracle")

            black_tags = json.loads(current[black_pearl]["tags_json"])
            self.assertEqual(
                black_tags["role:tenant"], "Amazon Web Services, Inc."
            )
            self.assertNotIn("role:user", black_tags)
            self.assertNotIn("role:customer", black_tags)

            pipeline = release_rows("role-safe-v3", "construction_pipeline.csv")
            self.assertEqual(pipeline[black_pearl]["users"], "")
            self.assertEqual(
                pipeline[black_pearl]["tenants"], "Amazon Web Services, Inc."
            )
            self.assertEqual(pipeline[black_pearl]["customers"], "")

            readme = (root / "role-safe-v3" / "README.md").read_text()
            self.assertIn("Role columns are dimensioned", readme)
            self.assertIn("A name in one role is not transferred to another", readme)
            self.assertIn("does not publish aggregate capacity totals", readme)
            summary = json.loads(
                (root / "role-safe-v3" / "summary.json").read_text()
            )
            self.assertNotIn("capacity_base_totals", summary)
            self.assertEqual(
                summary["capacity_aggregation"],
                {
                    "base_totals_published": False,
                    "cross_entity_sum_valid": False,
                    "reason": (
                        "Capacity rows can be nested, component-scoped, superseding, or "
                        "metric-distinct. Arithmetic sums are not valid facility, site, load, "
                        "energy, or unique-physical-site totals."
                    ),
                    "scope": "typed_source_observation_rows",
                },
            )
            manifest = json.loads(
                (root / "role-safe-v3" / "manifest.json").read_text()
            )
            for filename in (
                "entities.csv",
                "construction_pipeline.csv",
                "summary.json",
                "README.md",
            ):
                raw = (root / "role-safe-v3" / filename).read_bytes()
                self.assertEqual(manifest["files"][filename]["bytes"], len(raw))
                self.assertEqual(
                    manifest["files"][filename]["sha256"],
                    hashlib.sha256(raw).hexdigest(),
                )

    def test_unknown_publication_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            connection, _ = initialize(root / "atlas.sqlite")
            try:
                with self.assertRaisesRegex(
                    ValueError, "publication_contract_version must be one of"
                ):
                    write_release(
                        connection,
                        root / "release",
                        as_of="2026-07-17",
                        recorded_at="2026-07-17T13:00:00Z",
                        publication_contract_version=4,
                    )
                self.assertFalse((root / "release").exists())
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
