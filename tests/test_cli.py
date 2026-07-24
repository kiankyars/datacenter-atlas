from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from datacenter_atlas.cli import build_parser, main


FIXTURE = Path(__file__).parent / "fixtures" / "osm_minimal.json"
CURATED_FIXTURE = Path(__file__).parent / "fixtures" / "curated_official.json"


class CLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.db_path = root / "atlas.sqlite"
        self.geojson_path = root / "atlas.geojson"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def invoke(self, *arguments: str) -> tuple[int, dict[str, object]]:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(arguments)
        return code, json.loads(output.getvalue())

    def test_full_cli_workflow(self) -> None:
        code, initialized = self.invoke("init-db", "--db", str(self.db_path))
        self.assertEqual(code, 0)
        self.assertEqual(initialized["schema_version"], 2)

        code, imported = self.invoke(
            "import-osm",
            "--db",
            str(self.db_path),
            "--input",
            str(FIXTURE),
            "--retrieved-at",
            "2026-07-17T12:00:00-07:00",
        )
        self.assertEqual(code, 0)
        self.assertEqual(imported["imported_elements"], 3)

        code, validation = self.invoke("validate", "--db", str(self.db_path))
        self.assertEqual(code, 0)
        self.assertEqual(validation, {"errors": [], "valid": True})

        code, summary = self.invoke(
            "summary",
            "--db",
            str(self.db_path),
            "--as-of",
            "2026-07-17",
            "--recorded-at",
            "2026-07-18T00:00:00Z",
        )
        self.assertEqual(code, 0)
        self.assertEqual(summary["entities_total"], 6)

        code, exported = self.invoke(
            "export-geojson",
            "--db",
            str(self.db_path),
            "--output",
            str(self.geojson_path),
            "--as-of",
            "2026-07-17",
            "--recorded-at",
            "2026-07-18T00:00:00Z",
        )
        self.assertEqual(code, 0)
        self.assertEqual(exported["features"], 6)
        document = json.loads(self.geojson_path.read_text())
        self.assertEqual(document["type"], "FeatureCollection")

    def test_retrieval_timestamp_requires_timezone(self) -> None:
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main(
                    (
                        "import-osm",
                        "--db",
                        str(self.db_path),
                        "--input",
                        str(FIXTURE),
                        "--retrieved-at",
                        "2026-07-17T12:00:00",
                    )
                )

    def test_timestamp_parser_canonicalizes_offsets_and_rejects_fractions(self) -> None:
        args = build_parser().parse_args(
            (
                "import-osm",
                "--db",
                str(self.db_path),
                "--input",
                str(FIXTURE),
                "--retrieved-at",
                "2026-07-17T13:00:00.000+01:00",
            )
        )
        self.assertEqual(args.retrieved_at, "2026-07-17T12:00:00Z")

        for cutoff in (
            "2026-07-17T12:00:00.5Z",
            "2026-07-17T12:00:00.0000001Z",
        ):
            with self.subTest(rejected_timestamp=cutoff):
                with redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        build_parser().parse_args(
                            (
                                "summary",
                                "--db",
                                str(self.db_path),
                                "--recorded-at",
                                cutoff,
                            )
                        )

    def test_epoch_import_command_is_available(self) -> None:
        args = build_parser().parse_args(
            (
                "import-epoch",
                "--db",
                str(self.db_path),
                "--input",
                "epoch.zip",
                "--retrieved-at",
                "2026-07-18T00:58:43Z",
                "--as-of",
                "2026-07-17",
            )
        )
        self.assertEqual(args.command, "import-epoch")
        self.assertEqual(args.as_of, "2026-07-17")

    def test_curated_import_and_resolution_report(self) -> None:
        code, imported = self.invoke(
            "import-curated",
            "--db",
            str(self.db_path),
            "--input",
            str(CURATED_FIXTURE),
            "--retrieved-at",
            "2026-07-17T18:30:00Z",
        )
        self.assertEqual(code, 0)
        self.assertEqual(imported["imported_elements"], 1)
        output = self.geojson_path.with_name("resolution.json")
        code, report = self.invoke(
            "resolution-report",
            "--db",
            str(self.db_path),
            "--output",
            str(output),
            "--as-of",
            "2026-07-17",
            "--recorded-at",
            "2026-07-17T18:30:00Z",
        )
        self.assertEqual(code, 0)
        self.assertEqual(report["format"], "json")
        self.assertEqual(json.loads(output.read_text()), [])

    def test_ohsome_import_command_defaults_to_complete_bundle(self) -> None:
        args = build_parser().parse_args(
            (
                "import-ohsome",
                "--db",
                str(self.db_path),
                "--input",
                "saved-ohsome",
                "--retrieved-at",
                "2026-07-18T00:00:00Z",
            )
        )
        self.assertEqual(args.command, "import-ohsome")
        self.assertFalse(args.allow_partial)


if __name__ == "__main__":
    unittest.main()
