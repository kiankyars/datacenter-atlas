from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from datacenter_atlas.cli import build_parser
from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.publication_release import write_release
from datacenter_atlas.release import write_release as write_legacy_release
from scripts.build_open_seed import parser as build_open_seed_parser


ROOT = Path(__file__).resolve().parents[1]

BLACK_PEARL = (
    "curated:cipher-digital-black-pearl-wink-texas-data-center-campus:"
    "aws-phase-1-retrofit"
)
KORIA = "curated:hyperco-dayone-koria-unnamed-data-center-campus:current-build"
SALINE = "curated:related-openai-oracle-stargate-michigan-saline:current-build"

CAPACITY_AGGREGATION = {
    "base_totals_published": False,
    "cross_entity_sum_valid": False,
    "reason": (
        "Capacity rows can be nested, component-scoped, superseding, or "
        "metric-distinct. Arithmetic sums are not valid facility, site, load, "
        "energy, or unique-physical-site totals."
    ),
    "scope": "typed_source_observation_rows",
}


def release_rows(directory: Path, filename: str) -> dict[str, dict[str, str]]:
    with (directory / filename).open(newline="", encoding="utf-8") as stream:
        return {row["stable_key"]: row for row in csv.DictReader(stream)}


def release_bytes(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in directory.iterdir()}


class PublicationContractV4Tests(unittest.TestCase):
    def _import_role_fixture(self, connection) -> None:
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
                ROOT / "sources" / filename,
                retrieved_at=retrieved_at,
            )

    def test_v4_is_manifested_and_inherits_v3_roles_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            connection, _ = initialize(root / "atlas.sqlite")
            try:
                self._import_role_fixture(connection)
                for version in (1, 2, 3):
                    write_legacy_release(
                        connection,
                        root / f"legacy-v{version}",
                        as_of="2026-07-20",
                        recorded_at="2026-07-20T02:15:00Z",
                        publication_contract_version=version,
                    )
                    write_release(
                        connection,
                        root / f"dispatch-v{version}",
                        as_of="2026-07-20",
                        recorded_at="2026-07-20T02:15:00Z",
                        publication_contract_version=version,
                    )
                write_release(
                    connection,
                    root / "contract-v4",
                    as_of="2026-07-20",
                    recorded_at="2026-07-20T02:15:00Z",
                    publication_contract_version=4,
                )
            finally:
                connection.close()

            for version in (1, 2, 3):
                self.assertEqual(
                    release_bytes(root / f"dispatch-v{version}"),
                    release_bytes(root / f"legacy-v{version}"),
                )

            v2 = release_rows(root / "dispatch-v2", "entities.csv")
            self.assertNotIn("tenants", v2[BLACK_PEARL])
            self.assertNotIn("customers", v2[BLACK_PEARL])
            self.assertEqual(v2[BLACK_PEARL]["users"], "Amazon Web Services, Inc.")
            self.assertEqual(v2[SALINE]["users"], "OpenAI; Oracle")

            v3_directory = root / "dispatch-v3"
            v4_directory = root / "contract-v4"
            v3 = release_rows(v3_directory, "entities.csv")
            v4 = release_rows(v4_directory, "entities.csv")
            self.assertEqual(v4, v3)
            self.assertEqual(v4[KORIA]["users"], "TikTok")
            self.assertEqual(v4[KORIA]["tenants"], "")
            self.assertEqual(v4[KORIA]["customers"], "")
            self.assertEqual(v4[BLACK_PEARL]["users"], "")
            self.assertEqual(v4[BLACK_PEARL]["tenants"], "Amazon Web Services, Inc.")
            self.assertEqual(v4[BLACK_PEARL]["customers"], "")
            self.assertEqual(v4[SALINE]["users"], "")
            self.assertEqual(v4[SALINE]["tenants"], "")
            self.assertEqual(v4[SALINE]["customers"], "OpenAI; Oracle")
            self.assertEqual(
                release_rows(v4_directory, "construction_pipeline.csv"),
                release_rows(v3_directory, "construction_pipeline.csv"),
            )

            v3_summary_raw = (v3_directory / "summary.json").read_bytes()
            v4_summary_raw = (v4_directory / "summary.json").read_bytes()
            self.assertEqual(v4_summary_raw, v3_summary_raw)
            v4_summary = json.loads(v4_summary_raw)
            self.assertNotIn("capacity_base_totals", v4_summary)
            self.assertEqual(v4_summary["capacity_aggregation"], CAPACITY_AGGREGATION)

            v3_manifest = json.loads((v3_directory / "manifest.json").read_text())
            v4_manifest = json.loads((v4_directory / "manifest.json").read_text())
            self.assertNotIn("publication_contract_version", v3_manifest)
            self.assertIs(type(v4_manifest["publication_contract_version"]), int)
            self.assertEqual(v4_manifest["publication_contract_version"], 4)
            self.assertEqual(
                set(v4_manifest), set(v3_manifest) | {"publication_contract_version"}
            )

            v3_readme = (v3_directory / "README.md").read_text()
            v4_readme = (v4_directory / "README.md").read_text()
            self.assertEqual(v3_readme.count("contract v3"), 2)
            self.assertNotIn("contract v4", v3_readme)
            self.assertEqual(v4_readme.count("contract v4"), 2)
            self.assertNotIn("contract v3", v4_readme)
            self.assertNotIn("current release view", v4_readme)
            self.assertNotIn("active/pre-construction view", v4_readme)
            self.assertIn("source-scoped release", v4_readme)
            self.assertIn("latest-recorded pipeline-status view", v4_readme)
            self.assertIn(
                "inclusion does not confirm that the status persisted to the release date",
                v4_readme,
            )

            for filename, facts in v4_manifest["files"].items():
                raw = (v4_directory / filename).read_bytes()
                self.assertEqual(facts, {
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                })
                if filename != "README.md":
                    self.assertEqual(raw, (v3_directory / filename).read_bytes())

    def test_v4_keeps_custom_readme_verbatim_and_hashes_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            connection, _ = initialize(root / "atlas.sqlite")
            custom_readme = "# Contract v4 custom publication\n\nExact scope text.\n"
            try:
                write_release(
                    connection,
                    root / "release",
                    as_of="2026-07-20",
                    recorded_at="2026-07-20T02:15:00Z",
                    readme=custom_readme,
                    publication_contract_version=4,
                )
            finally:
                connection.close()

            raw = (root / "release" / "README.md").read_bytes()
            manifest = json.loads((root / "release" / "manifest.json").read_text())
            self.assertEqual(raw, custom_readme.encode("utf-8"))
            self.assertEqual(manifest["publication_contract_version"], 4)
            self.assertEqual(
                manifest["files"]["README.md"],
                {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
            )

    def test_v4_empty_readme_matches_generated_readme(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            connection, _ = initialize(root / "atlas.sqlite")
            try:
                write_release(
                    connection,
                    root / "generated",
                    as_of="2026-07-20",
                    recorded_at="2026-07-20T02:15:00Z",
                    publication_contract_version=4,
                )
                write_release(
                    connection,
                    root / "empty",
                    as_of="2026-07-20",
                    recorded_at="2026-07-20T02:15:00Z",
                    readme="",
                    publication_contract_version=4,
                )
            finally:
                connection.close()

            self.assertEqual(
                release_bytes(root / "empty"),
                release_bytes(root / "generated"),
            )
            readme = (root / "empty" / "README.md").read_text()
            self.assertEqual(readme.count("contract v4"), 2)
            self.assertNotIn("contract v3", readme)

    def test_contract_four_is_cli_selectable_and_five_is_rejected(self) -> None:
        cli_args = build_parser().parse_args(
            [
                "export-release",
                "--db",
                "atlas.sqlite",
                "--output-dir",
                "release",
                "--publication-contract-version",
                "4",
            ]
        )
        self.assertEqual(cli_args.publication_contract_version, 4)

        script_args = build_open_seed_parser().parse_args(
            [
                "--epoch-input",
                "epoch.zip",
                "--epoch-retrieved-at",
                "2026-07-20T00:00:00Z",
                "--curated-dir",
                "sources",
                "--output-dir",
                "release",
                "--as-of",
                "2026-07-20",
                "--recorded-at",
                "2026-07-20T02:15:00Z",
                "--publication-contract-version",
                "4",
            ]
        )
        self.assertEqual(script_args.publication_contract_version, 4)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            connection, _ = initialize(root / "atlas.sqlite")
            try:
                with self.assertRaisesRegex(
                    ValueError,
                    "publication_contract_version must be one of: 1, 2, 3, 4",
                ):
                    write_release(
                        connection,
                        root / "release",
                        as_of="2026-07-20",
                        recorded_at="2026-07-20T02:15:00Z",
                        publication_contract_version=5,
                    )
                self.assertFalse((root / "release").exists())
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
