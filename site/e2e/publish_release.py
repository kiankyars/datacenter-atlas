"""Publish or verify frozen snapshot assets before GitHub Pages uses their URLs.

Existing published releases are read-only. A new release is uploaded as a draft,
read back and checked, then published. A failed draft can resume without replacing
any asset. GitHub CLI supplies authentication; tokens never enter command arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import quote

import release_notes


class PublicationError(RuntimeError):
    pass


def sha256(body):
    return hashlib.sha256(body).hexdigest()


class GitHub:
    def __init__(self, repository):
        self.repository = repository

    def command(self, args):
        result = subprocess.run(["gh", *args], capture_output=True)
        if result.returncode:
            raise PublicationError(result.stderr.decode("utf-8", "replace").strip())
        return result.stdout

    def api(self, path, *, missing=False, raw=False, method=None, payload=None):
        args = ["gh", "api", f"repos/{self.repository}/{path}"]
        if raw:
            accept = "application/octet-stream" if path.startswith("releases/assets/") else "application/vnd.github.raw+json"
            args += ["-H", f"Accept: {accept}"]
        if method:
            args += ["--method", method]
        body = None
        if payload is not None:
            args += ["--input", "-"]
            body = json.dumps(payload).encode()
        result = subprocess.run(args, input=body, capture_output=True)
        if result.returncode:
            error = result.stderr.decode("utf-8", "replace").strip()
            if missing and "HTTP 404" in error:
                return None
            raise PublicationError(error)
        return result.stdout if raw else (json.loads(result.stdout) if result.stdout.strip() else None)


def find_release(github, tag):
    release = github.api(f"releases/tags/{tag}", missing=True)
    if release is not None:
        return release
    # The tag endpoint excludes drafts; authenticated list releases includes them.
    for page in range(1, 101):
        releases = github.api(f"releases?per_page=100&page={page}")
        matches = [item for item in releases if item.get("tag_name") == tag]
        if len(matches) > 1:
            raise PublicationError(f"Multiple releases use {tag}; leave them untouched")
        if matches:
            return matches[0]
        if len(releases) < 100:
            return None
    raise PublicationError("Release lookup exceeded its page bound")


def verify_public_downloads(inventory, *, read_bytes):
    """Read actual anonymous URLs; only transient publication lag is retried."""
    for item in inventory["files"]:
        for attempt in range(3):
            request = urllib.request.Request(item["url"], method="GET" if read_bytes else "HEAD",
                                             headers={"User-Agent": "DataCenterAtlas-release-verification"})
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    if response.status != 200:
                        raise PublicationError(f"Public release URL returned {response.status}: {item['name']}")
                    if read_bytes:
                        body = response.read(item["bytes"] + 1)
                        if len(body) != item["bytes"] or sha256(body) != item["sha256"]:
                            raise PublicationError(f"Public release bytes mismatch: {item['name']}")
                    elif response.headers.get("Content-Length") is not None:
                        if int(response.headers["Content-Length"]) != item["bytes"]:
                            raise PublicationError(f"Public release size mismatch: {item['name']}")
                break
            except urllib.error.HTTPError as error:
                if error.code not in (404, 502, 503, 504) or attempt == 2:
                    raise PublicationError(f"Public release URL failed: {item['name']} HTTP {error.code}") from None
                time.sleep(attempt + 1)


def checked_inventory(inventory, repository_url):
    identifier = inventory.get("dataset_id", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", identifier):
        raise PublicationError("Invalid inventory dataset identifier")
    tag = f"data-{identifier}"
    if (inventory.get("schema") != "datacenter-atlas-release-assets-v1"
            or inventory.get("repository_url") != repository_url
            or inventory.get("release_tag") != tag
            or not re.fullmatch(r"[0-9a-f]{64}", inventory.get("manifest_sha256", ""))):
        raise PublicationError(f"Invalid frozen inventory: {identifier}")
    files = inventory.get("files", [])
    names = [item.get("name", "") for item in files]
    if names != sorted(set(names)) or not {"manifest.json", "manifest.sha256", "SHA256SUMS",
                                          f"datacenter-atlas-{identifier}.zip"} <= set(names):
        raise PublicationError(f"Incomplete or duplicate inventory files: {identifier}")
    for item in files:
        name = item["name"]
        expected_url = f"{repository_url}/releases/download/{tag}/{quote(name, safe='')}"
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name)
                or type(item.get("bytes")) is not int or item["bytes"] < 0
                or not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", ""))
                or item.get("url") != expected_url):
            raise PublicationError(f"Invalid frozen asset: {identifier}/{name}")
    manifest = next(item for item in files if item["name"] == "manifest.json")
    if manifest["sha256"] != inventory["manifest_sha256"]:
        raise PublicationError(f"Manifest hash differs from inventory: {identifier}")
    return files


def check_staged(directory, inventory):
    expected = {item["name"]: item for item in inventory["files"]}
    if not directory.is_dir() or directory.is_symlink():
        raise PublicationError(f"Missing staged snapshot: {directory}")
    paths = list(directory.iterdir())
    if {path.name for path in paths} != set(expected):
        raise PublicationError(f"Staged asset names differ from frozen inventory: {directory}")
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise PublicationError(f"Staged asset is not a regular file: {path}")
        body = path.read_bytes()
        if len(body) != expected[path.name]["bytes"] or sha256(body) != expected[path.name]["sha256"]:
            raise PublicationError(f"Staged asset differs from frozen inventory: {path}")
    entries = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        if name in entries:
            raise PublicationError(f"Duplicate checksum: {name}")
        entries[name] = digest
    if entries != {name: item["sha256"] for name, item in expected.items() if name != "SHA256SUMS"}:
        raise PublicationError("SHA256SUMS does not cover the exact frozen asset set")


def verify_assets(github, release, inventory, *, download=False, allow_missing=False):
    assets = github.api(f"releases/{release['id']}/assets?per_page=100")
    by_name = {asset["name"]: asset for asset in assets}
    if len(by_name) != len(assets):
        raise PublicationError("Duplicate release asset names")
    expected = {item["name"]: item for item in inventory["files"]}
    if set(by_name) - set(expected):
        raise PublicationError("Release has unexpected assets")
    missing = set(expected) - set(by_name)
    if missing and not allow_missing:
        raise PublicationError(f"Release is missing assets: {sorted(missing)}")
    for name, asset in by_name.items():
        item = expected[name]
        if (asset.get("state") != "uploaded" or asset.get("size") != item["bytes"]
                or (not release.get("draft") and asset.get("browser_download_url") != item["url"])):
            raise PublicationError(f"Release metadata mismatch: {name}")
        digest = asset.get("digest")
        if digest is not None and digest != "sha256:" + item["sha256"]:
            raise PublicationError(f"Release digest mismatch: {name}")
        if download or digest is None:
            body = github.api(f"releases/assets/{asset['id']}", raw=True)
            if len(body) != item["bytes"] or sha256(body) != item["sha256"]:
                raise PublicationError(f"Downloaded release asset mismatch: {name}")
    return sorted(missing)


def verify_manifest_at_tag(github, inventory, versions_root):
    path = f"{versions_root}/{inventory['dataset_id']}/manifest.json"
    body = github.api(f"contents/{quote(path, safe='/')}?ref={quote(inventory['release_tag'], safe='')}", raw=True)
    if sha256(body) != inventory["manifest_sha256"]:
        raise PublicationError("Release tag does not contain the frozen dataset manifest")


def check_new_tag(github, tag, commit):
    reference = github.api(f"git/ref/tags/{tag}", missing=True)
    if reference is None:
        return
    obj = reference["object"]
    for _ in range(5):
        if obj["type"] != "tag":
            break
        obj = github.api(f"git/tags/{obj['sha']}")["object"]
    if obj.get("type") != "commit" or obj.get("sha") != commit:
        raise PublicationError("Existing tag belongs to another commit; leave it untouched")


def publish_inventory(github, inventory, *, staged_root, current, commit, title, notes, prerelease,
                      versions_root, public_verify=verify_public_downloads):
    tag = inventory["release_tag"]
    release = find_release(github, tag)
    if release is not None and not release.get("draft"):
        verify_assets(github, release, inventory)
        verify_manifest_at_tag(github, inventory, versions_root)
        public_verify(inventory, read_bytes=True)
        return "verified_existing"
    if inventory["dataset_id"] != current:
        raise PublicationError(f"Previously frozen release is absent or still a draft: {tag}")
    directory = staged_root / current
    check_staged(directory, inventory)
    check_new_tag(github, tag, commit)
    if release is None:
        release = github.api("releases", method="POST", payload={
            "tag_name": tag, "target_commitish": commit, "name": title,
            "body": notes, "draft": True, "prerelease": prerelease,
        })
    if release.get("target_commitish") != commit:
        raise PublicationError("Existing draft belongs to another commit; leave it untouched")
    # GitHub can leave empty starter records after an interrupted upload. Remove
    # only these known placeholders in this exact matching draft; never replace
    # completed or unexpected assets.
    expected_names = {item["name"] for item in inventory["files"]}
    for asset in github.api(f"releases/{release['id']}/assets?per_page=100"):
        if (asset.get("name") in expected_names and asset.get("state") == "starter"
                and asset.get("size") == 0 and not asset.get("digest")):
            github.api(f"releases/assets/{asset['id']}", method="DELETE")
    missing = verify_assets(github, release, inventory, download=True, allow_missing=True)
    if missing:
        github.command(["release", "upload", tag, *[str(directory / name) for name in missing],
                        "--repo", github.repository])
    verify_assets(github, release, inventory, download=True)
    github.api(f"releases/{release['id']}", method="PATCH", payload={"draft": False})
    published = github.api(f"releases/tags/{tag}")
    if published.get("draft"):
        raise PublicationError("Release did not become public")
    verify_assets(github, published, inventory)
    verify_manifest_at_tag(github, inventory, versions_root)
    public_verify(inventory, read_bytes=True)
    return "published_and_verified"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, required=True)
    parser.add_argument("--release-assets", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--enabled", choices=("true", "false"), required=True)
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
            raise PublicationError("An exact source commit is required")
        publication = json.loads((args.release_assets / "publication.json").read_text())
        if publication.get("schema") != "datacenter-atlas-release-publication-v1":
            raise PublicationError("Unknown release publication schema")
        index = json.loads((args.site / "api/v1/index.json").read_text())
        repository_url = publication["repository_url"]
        match = re.fullmatch(r"https://github.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", repository_url)
        if not match or repository_url != index["repository_url"]:
            raise PublicationError("Release repository does not match the site")
        repository = match.group(1)
        if os.environ.get("GITHUB_REPOSITORY", repository) != repository:
            raise PublicationError("Release repository does not match this workflow")
        current = index["dataset"]["id"]
        if publication["current_dataset"] != current:
            raise PublicationError("Publication inventory belongs to another current dataset")
        inventories = publication["inventories"]
        if len({item["dataset_id"] for item in inventories}) != len(inventories):
            raise PublicationError("Duplicate dataset inventories")
        for inventory in inventories:
            checked_inventory(inventory, repository_url)
        if args.enabled != "true":
            if inventories:
                raise PublicationError("Release-backed downloads require ATLAS_GITHUB_RELEASES=true")
            print("GitHub Releases are disabled; no remote downloads depend on them.")
            return 0
        github = GitHub(repository)
        versions = json.loads((args.site / "api/v1/versions.json").read_text())
        sites = json.loads((args.site / "api/v1/sites.json").read_text())
        citation = json.loads((args.site / "api/v1/citation.json").read_text())
        dataset = index["dataset"]
        notes = release_notes.notes(index, versions, sites, commit=args.commit, citation=citation)
        title = release_notes.release_title(dataset)
        prerelease = release_notes.is_prerelease(dataset)
        versions_root = dataset["repository_path"].rsplit("/", 1)[0]
        for inventory in inventories:
            result = publish_inventory(github, inventory, staged_root=args.release_assets,
                                       current=current, commit=args.commit, title=title, notes=notes,
                                       prerelease=prerelease, versions_root=versions_root)
            print(f"{inventory['release_tag']}: {result} ({len(inventory['files'])} assets)")
        if current not in {item["dataset_id"] for item in inventories}:
            tag = release_notes.release_tag(current)
            if find_release(github, tag) is not None:
                print(f"Legacy release {tag} already exists; preserved unchanged.")
            else:
                assets = release_notes.asset_paths(args.site, current)
                with tempfile.TemporaryDirectory(prefix="atlas-release-") as folder:
                    notes_path = Path(folder) / "notes.md"
                    notes_path.write_text(notes)
                    flags = ["--prerelease"] if prerelease else []
                    github.command(["release", "create", tag, *map(str, assets), "--repo", repository,
                                    "--target", args.commit, "--title", title,
                                    "--notes-file", str(notes_path), *flags])
                print(f"Created legacy release {tag} with {len(assets)} assets.")
    except (PublicationError, OSError, ValueError, KeyError, release_notes.ReleaseError) as error:
        print(f"publish_release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
