"""Clean-clone safety: Git tracks every file a dataset manifest lists, and .gitignore allows them."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_tracked_dataset_files", ROOT / "scripts" / "check_tracked_dataset_files.py")
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)


def _is_checkout(root: Path) -> bool:
    if shutil.which("git") is None:
        return False
    result = _git(root, "rev-parse", "--show-toplevel")
    return result.returncode == 0 and Path(result.stdout.decode().strip()).resolve() == root.resolve()


class RepositoryTrackingTests(unittest.TestCase):
    def setUp(self):
        if not _is_checkout(ROOT):
            self.skipTest("not a Git checkout of the repository")

    def test_every_manifest_listed_dataset_file_is_tracked(self):
        problems = check.untracked_manifest_files(ROOT)
        self.assertEqual(problems, [], "\n".join(problems))

    def test_gitignore_allows_provenance_files_of_any_new_dataset_and_denies_the_rest(self):
        new = "verified_construction_core/2099-01-01-research-example"
        for name in ("review-provenance.json", "source-records.json", "identity-mapping.json",
                     "manifest.json", "sites.csv", "ATTRIBUTION.txt"):
            with self.subTest(name=name):
                # Exit status 1: the path is not ignored.
                self.assertEqual(_git(ROOT, "check-ignore", "--no-index", "-q", f"{new}/{name}").returncode, 1)
        for path in (f"{new}/atlas.sqlite", f"{new}/nested/source-records.json", "verified_construction_core/x.json",
                     f"{new}/source-records.json.bak"):
            with self.subTest(path=path):
                self.assertEqual(_git(ROOT, "check-ignore", "--no-index", "-q", path).returncode, 0)

    def test_gitignore_has_no_per_release_provenance_rules(self):
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        per_release = [line for line in lines if line.startswith("!/verified_construction_core/")
                       and line != "!/verified_construction_core/"
                       and not line.startswith("!/verified_construction_core/*/")]
        self.assertEqual(per_release, [])


class SyntheticRepositoryTests(unittest.TestCase):
    def setUp(self):
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        self.temp = tempfile.TemporaryDirectory(prefix="atlas-tracking-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assertEqual(_git(self.root, "init", "-q").returncode, 0)
        (self.root / "site").mkdir()
        (self.root / "site/config.json").write_text(json.dumps({"versions_root": "data"}))
        self.dataset = self.root / "data/2026-01-02-update"
        self.dataset.mkdir(parents=True)
        for name in ("sites.csv", "source-records.json", "manifest.sha256"):
            (self.dataset / name).write_text("x\n")
        (self.root / "definitions").mkdir()
        (self.root / "definitions/update.json").write_text("{}\n")
        (self.root / "sources").mkdir()
        (self.root / "sources/packet.json").write_text("{}\n")
        self.manifest = {
            "format": "datacenter-atlas-update-v1",
            "files": {"sites.csv": {}, "source-records.json": {}},
            "input_path": "definitions/update.json",
            "source_files": [{"path": "sources/packet.json", "sha256": "0" * 64}],
        }
        self.write_manifest()

    def write_manifest(self):
        (self.dataset / "manifest.json").write_text(json.dumps(self.manifest))

    def add(self, *paths: str):
        self.assertEqual(_git(self.root, "add", "-f", *paths).returncode, 0)

    def test_untracked_listed_files_and_update_inputs_are_named(self):
        self.add("data/2026-01-02-update/manifest.json", "data/2026-01-02-update/manifest.sha256",
                 "data/2026-01-02-update/sites.csv")
        problems = check.untracked_manifest_files(self.root)
        self.assertEqual(problems, [
            "data/2026-01-02-update/source-records.json (listed by data/2026-01-02-update/manifest.json) "
            "is not tracked by Git",
            "definitions/update.json (listed by data/2026-01-02-update/manifest.json) is not tracked by Git",
            "sources/packet.json (listed by data/2026-01-02-update/manifest.json) is not tracked by Git",
        ])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check.main(["--root", str(self.root)]), 1)
        self.assertIn("source-records.json", stderr.getvalue())
        self.assertIn("git add", stderr.getvalue())
        self.add("data/2026-01-02-update/source-records.json", "definitions/update.json", "sources/packet.json")
        self.assertEqual(check.untracked_manifest_files(self.root), [])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check.main(["--root", str(self.root)]), 0)

    def test_historical_formats_check_only_their_listed_files(self):
        self.manifest = {"release_status": "draft", "files": {"sites.csv": {}}, "input_path": "missing.json"}
        self.write_manifest()
        self.add("data/2026-01-02-update/manifest.json", "data/2026-01-02-update/manifest.sha256",
                 "data/2026-01-02-update/sites.csv")
        self.assertEqual(check.untracked_manifest_files(self.root), [])

    def test_unsafe_manifest_paths_and_non_checkouts_fail_closed(self):
        for manifest in ({**self.manifest, "input_path": "../outside.json"},
                         {**self.manifest, "files": {"../escape.csv": {}}},
                         {**self.manifest, "source_files": [{"path": "/etc/passwd"}]}):
            with self.subTest(manifest=manifest):
                self.manifest = manifest
                self.write_manifest()
                with self.assertRaises(check.TrackingError):
                    check.untracked_manifest_files(self.root)
        with tempfile.TemporaryDirectory() as plain:
            with self.assertRaisesRegex(check.TrackingError, "not a Git checkout"):
                check.tracked_files(Path(plain))


if __name__ == "__main__":
    unittest.main()
