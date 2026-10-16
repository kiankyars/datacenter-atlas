"""Seal a frozen inventory for a legacy GitHub Release that already holds a dated archive.

A legacy release (a version before ``release_downloads_from``) attached a selection of the files
its ``downloads/<id>/`` directory held when that version was current: the zip, ``SHA256SUMS``, the
CSVs and GeoJSON, SQLite, Excel, JSON and the Data Package. Those assets are frozen, while the
site's own copies of the derived formats are rebuilt by every build. This tool reads one existing
published release with the GitHub CLI, downloads every asset, checks each one against GitHub's
digest, the release's own ``SHA256SUMS``, the zip's members and the dataset's tracked manifest,
and writes ``site/release-inventories/<id>.json`` with schema
``datacenter-atlas-legacy-release-assets-v1``.

The inventory also records ``local_files``: the derived formats (JSON, NDJSON, SQLite, Excel, KML,
Data Package; never the zip) that this checkout's site builder still writes byte for byte as the
release's ``SHA256SUMS`` lists them, for the configured base URL. With that inventory the site
builder keeps the version's original files, a byte-identical ``SHA256SUMS`` and those
``local_files`` (checked on every build) at their existing Pages URLs, links its other derived
formats and its zip to the frozen release assets, and stops publishing rebuilt copies that no
longer match. The publication gate verifies the release before every deployment.

The tool only reads: it never creates, edits or uploads a release, and it refuses to overwrite an
existing inventory. GitHub CLI supplies authentication.

Usage (standard library only)::

    python3 site/e2e/seal_legacy_release.py --dataset 2026-10-13-research [--dataset ...]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Sequence
import zipfile

import publish_release

SCHEMA = "datacenter-atlas-legacy-release-assets-v1"
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
SHA256_LINE = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._-]*)")
REPO_ROOT = Path(__file__).resolve().parents[2]
# The site builder's derived formats (public_site.DERIVED_DOWNLOADS); only these can stay local.
DERIVED_FORMATS = frozenset({
    "atlas.json", "atlas.sqlite", "atlas.xlsx", "sites.kml", "sites.ndjson", "projects.ndjson",
    "evidence.ndjson", "datapackage.json",
})


class SealError(RuntimeError):
    pass


def sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sha256sums_bytes(entries: Sequence[Mapping[str, str]]) -> bytes:
    """GNU-format SHA256SUMS text for name-sorted entries, as the site builder writes it."""
    return "".join(f"{item['sha256']}  {item['name']}\n" for item in entries).encode("ascii")


def parse_sha256sums(body: bytes) -> list[dict[str, str]]:
    """Strictly parse a builder-written SHA256SUMS: sorted, unique, safe names, exact bytes."""
    try:
        text = body.decode("ascii")
    except UnicodeDecodeError as error:
        raise SealError(f"SHA256SUMS is not ASCII: {error}") from None
    entries = []
    for line in text.splitlines():
        match = SHA256_LINE.fullmatch(line)
        if match is None:
            raise SealError(f"unexpected SHA256SUMS line: {line!r}")
        entries.append({"name": match.group(2), "sha256": match.group(1)})
    names = [item["name"] for item in entries]
    if not entries or names != sorted(set(names)) or "SHA256SUMS" in names:
        raise SealError("SHA256SUMS must list unique, sorted names and not itself")
    if sha256sums_bytes(entries) != body:
        raise SealError("SHA256SUMS bytes are not in the builder's canonical format")
    return entries


def release_url(repository_url: str, dataset_id: str, name: str) -> str:
    return f"{repository_url}/releases/download/data-{dataset_id}/{name}"


def legacy_inventory(*, dataset_id: str, repository_url: str, manifest_sha256: str,
                     originals: Mapping[str, str], assets: Sequence[Mapping[str, Any]],
                     bodies: Mapping[str, bytes], rebuilt: Mapping[str, str]) -> dict[str, Any]:
    """Check one downloaded legacy release offline and return its inventory document.

    ``originals`` maps every manifest-listed file (plus manifest.json and manifest.sha256) to
    its SHA-256; ``assets`` are GitHub's asset records and ``bodies`` the downloaded bytes.
    ``rebuilt`` maps each derived format to the SHA-256 of the site builder's copy; those equal
    to the release's SHA256SUMS become ``local_files``.
    """
    if not SAFE_NAME.fullmatch(dataset_id):
        raise SealError(f"unsafe dataset identifier {dataset_id!r}")
    by_name: dict[str, Mapping[str, Any]] = {}
    for asset in assets:
        name = asset.get("name")
        if not isinstance(name, str) or not SAFE_NAME.fullmatch(name) or name in by_name:
            raise SealError(f"unsafe or duplicate release asset name {name!r}")
        by_name[name] = asset
    zip_name = f"datacenter-atlas-{dataset_id}.zip"
    for required in ("SHA256SUMS", zip_name):
        if required not in by_name:
            raise SealError(f"data-{dataset_id} has no {required} asset")
    files = []
    for name in sorted(by_name):
        asset, body = by_name[name], bodies.get(name)
        if body is None:
            raise SealError(f"{name} was not downloaded")
        digest = sha256(body)
        if asset.get("state") != "uploaded" or asset.get("size") != len(body):
            raise SealError(f"{name}: GitHub reports state {asset.get('state')} and {asset.get('size')} bytes, "
                            f"downloaded {len(body)}")
        if asset.get("digest") is not None and asset["digest"] != "sha256:" + digest:
            raise SealError(f"{name}: downloaded bytes differ from GitHub's digest")
        url = release_url(repository_url, dataset_id, name)
        if asset.get("browser_download_url") != url:
            raise SealError(f"{name}: unexpected download URL {asset.get('browser_download_url')}")
        files.append({"name": name, "bytes": len(body), "sha256": digest, "url": url})
    sums = parse_sha256sums(bodies["SHA256SUMS"])
    listed = {item["name"]: item["sha256"] for item in sums}
    for item in files:
        if item["name"] != "SHA256SUMS" and listed.get(item["name"]) != item["sha256"]:
            raise SealError(f"{item['name']}: release asset differs from the release's SHA256SUMS")
    if zip_name not in listed:
        raise SealError(f"SHA256SUMS does not list {zip_name}")
    with zipfile.ZipFile(io.BytesIO(bodies[zip_name])) as archive:
        # The zip holds every file of the directory except SHA256SUMS and itself.
        members = archive.namelist()
        if members != sorted(name for name in listed if name != zip_name) or len(set(members)) != len(members):
            raise SealError(f"{zip_name} members differ from SHA256SUMS")
        for member in members:
            if sha256(archive.read(member)) != listed[member]:
                raise SealError(f"{zip_name}: member {member} differs from SHA256SUMS")
    if originals.get("manifest.json") != manifest_sha256:
        raise SealError("manifest.json hash differs from the dataset manifest")
    for name, digest in sorted(originals.items()):
        if listed.get(name) != digest:
            raise SealError(f"original {name} in the release differs from the tracked dataset")
    if not set(rebuilt) <= DERIVED_FORMATS:
        raise SealError(f"not derived formats: {sorted(set(rebuilt) - DERIVED_FORMATS)}")
    local_files = sorted(name for name, digest in rebuilt.items() if name in listed and listed[name] == digest)
    return {
        "schema": SCHEMA,
        "dataset_id": dataset_id,
        "manifest_sha256": manifest_sha256,
        "release_tag": f"data-{dataset_id}",
        "repository_url": repository_url,
        "files": files,
        "sha256sums": sums,
        "local_files": local_files,
    }


def _originals(directory: Path) -> tuple[str, dict[str, str]]:
    manifest_bytes = (directory / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    originals = {name: entry["sha256"] for name, entry in manifest["files"].items()}
    originals["manifest.json"] = sha256(manifest_bytes)
    originals["manifest.sha256"] = sha256((directory / "manifest.sha256").read_bytes())
    for name, digest in originals.items():
        if sha256((directory / name).read_bytes()) != digest:
            raise SealError(f"{directory / name} differs from its manifest")
    return originals["manifest.json"], originals


def builder_digests(root: Path, dataset_id: str) -> dict[str, str]:
    """SHA-256 of each derived format as this checkout's site builder writes it (offline)."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from datacenter_atlas import public_site

    try:
        return public_site.rebuilt_derived_digests([dataset_id], root=root)[dataset_id]
    except public_site.PublicSiteError as error:
        raise SealError(str(error)) from None


def seal(github: publish_release.GitHub, *, dataset_id: str, repository_url: str, versions_root: str,
         root: Path, output: Path,
         rebuilt: Callable[[Path, str], Mapping[str, str]] = builder_digests) -> dict[str, Any]:
    if output.exists():
        raise SealError(f"{output} exists; a sealed inventory is never replaced")
    manifest_sha256, originals = _originals(root / versions_root / dataset_id)
    tag = f"data-{dataset_id}"
    release = github.api(f"releases/tags/{tag}", missing=True)
    if release is None or release.get("draft") or release.get("tag_name") != tag:
        raise SealError(f"{tag} is not a published release")
    assets = github.api(f"releases/{release['id']}/assets?per_page=100")
    if len(assets) >= 100:
        raise SealError(f"{tag} has too many assets for one page")
    bodies = {asset["name"]: github.api(f"releases/assets/{asset['id']}", raw=True) for asset in assets}
    inventory = legacy_inventory(dataset_id=dataset_id, repository_url=repository_url,
                                 manifest_sha256=manifest_sha256, originals=originals, assets=assets,
                                 bodies=bodies, rebuilt=rebuilt(root, dataset_id))
    publish_release.verify_manifest_at_tag(github, inventory, versions_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")
    return inventory


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seal inventories for existing legacy GitHub Releases.")
    parser.add_argument("--dataset", action="append", required=True, help="dataset ID; repeat for several")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root (default: this checkout)")
    args = parser.parse_args(argv)
    try:
        config = json.loads((args.root / "site/config.json").read_text(encoding="utf-8"))
        repository_url = config["repository_url"].rstrip("/")
        match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", repository_url)
        if not match:
            raise SealError("repository_url must be a canonical https://github.com/owner/repository URL")
        github = publish_release.GitHub(match.group(1))
        for dataset_id in args.dataset:
            output = args.root / "site/release-inventories" / f"{dataset_id}.json"
            inventory = seal(github, dataset_id=dataset_id, repository_url=repository_url,
                             versions_root=config["versions_root"], root=args.root, output=output)
            print(f"{output.relative_to(args.root)}: {len(inventory['files'])} assets, "
                  f"{len(inventory['sha256sums'])} checksums, {len(inventory['local_files'])} local files")
    except (SealError, publish_release.PublicationError, OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
        print(f"seal_legacy_release: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
