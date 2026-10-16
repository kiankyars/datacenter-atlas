"""Offline tests for publication order, frozen assets, and failed-run recovery."""

import copy
import io
import json
from pathlib import Path
import sys
import zipfile

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import publish_release as publication  # noqa: E402 -- load adjacent CI helpers after adding their directory
import check_pages_size  # noqa: E402
import seal_legacy_release as sealing  # noqa: E402

REPO = "https://github.com/example/atlas"
IDENTIFIER = "2026-10-15-research"
COMMIT = "a" * 40


@pytest.fixture
def snapshot(tmp_path):
    directory = tmp_path / IDENTIFIER
    directory.mkdir()
    bodies = {"manifest.json": b'{"original":true}\n', "manifest.sha256": b"manifest hash\n",
              f"datacenter-atlas-{IDENTIFIER}.zip": b"frozen zip bytes"}
    bodies["SHA256SUMS"] = "".join(f"{publication.sha256(body)}  {name}\n"
                                      for name, body in sorted(bodies.items())).encode()
    for name, body in bodies.items():
        (directory / name).write_bytes(body)
    inventory = {"schema": "datacenter-atlas-release-assets-v1", "dataset_id": IDENTIFIER,
                 "repository_url": REPO, "release_tag": f"data-{IDENTIFIER}",
                 "manifest_sha256": publication.sha256(bodies["manifest.json"]),
                 "files": [{"name": name, "bytes": len(body), "sha256": publication.sha256(body),
                            "url": f"{REPO}/releases/download/data-{IDENTIFIER}/{name}"}
                           for name, body in sorted(bodies.items())]}
    return tmp_path, inventory, bodies


class FakeGitHub:
    repository = "example/atlas"

    def __init__(self, bodies, inventory, *, existing=False, draft=False):
        self.bodies = bodies
        self.inventory = inventory
        self.release = {"id": 7, "draft": draft, "target_commitish": COMMIT} if existing else None
        self.assets = self.make_assets() if existing else []
        self.events = []
        self.tag_commit = None
        self.corrupt_download = False

    def make_assets(self):
        return [{"id": i, "name": item["name"], "state": "uploaded", "size": item["bytes"],
                 "digest": "sha256:" + item["sha256"], "browser_download_url": item["url"]}
                for i, item in enumerate(self.inventory["files"], 20)]

    def api(self, path, **options):
        self.events.append((path, options))
        if path.startswith("releases/tags/"):
            return copy.deepcopy(self.release) if self.release and not self.release["draft"] else None
        if path.startswith("releases?per_page=100&page="):
            return [{**self.release, "tag_name": self.inventory["release_tag"]}] if self.release else []
        if path.startswith("git/ref/tags/"):
            return {"object": {"type": "commit", "sha": self.tag_commit}} if self.tag_commit else None
        if path == "releases":
            assert options["payload"]["draft"] is True
            self.release = {"id": 7, "draft": True, "target_commitish": options["payload"]["target_commitish"]}
            return copy.deepcopy(self.release)
        if path == "releases/7/assets?per_page=100":
            return copy.deepcopy(self.assets)
        if path.startswith("releases/assets/"):
            asset = next(item for item in self.assets if str(item["id"]) == path.rsplit("/", 1)[1])
            if options.get("method") == "DELETE":
                self.assets.remove(asset)
                return None
            return b"corrupted" if self.corrupt_download else self.bodies[asset["name"]]
        if path == "releases/7":
            assert options["method"] == "PATCH"
            self.release["draft"] = options["payload"]["draft"]
            return copy.deepcopy(self.release)
        if path.startswith("contents/"):
            return self.bodies["manifest.json"]
        raise AssertionError(path)

    def command(self, args):
        self.events.append(("command", args))
        assert args[:3] == ["release", "upload", self.inventory["release_tag"]]
        assert "--clobber" not in args
        names = [Path(path).name for path in args[3:args.index("--repo")]]
        assert not set(names) & {item["name"] for item in self.assets}
        self.assets += [item for item in self.make_assets() if item["name"] in names]


def publish(github, snapshot):
    root, inventory, _ = snapshot
    def verify_public(value, *, read_bytes):
        assert read_bytes is True and value == inventory
        github.events.append(("public_downloads", {}))
    return publication.publish_inventory(github, inventory, staged_root=root, current=IDENTIFIER,
                                         commit=COMMIT, title="Snapshot", notes="Test notes", prerelease=False,
                                         versions_root="verified_construction_core", public_verify=verify_public)


def test_new_release_is_read_back_before_publication(snapshot):
    _, inventory, bodies = snapshot
    github = FakeGitHub(bodies, inventory)
    assert publish(github, snapshot) == "published_and_verified"
    publish_index = next(i for i, event in enumerate(github.events) if event[0] == "releases/7")
    reads = [path for path, _ in github.events[:publish_index] if path.startswith("releases/assets/")]
    assert len(reads) == len(bodies)
    assert github.release["draft"] is False
    assert github.events[-1][0] == "public_downloads"


def test_existing_release_uses_frozen_inventory_despite_changed_local_derivation(snapshot):
    root, inventory, bodies = snapshot
    (root / IDENTIFIER / f"datacenter-atlas-{IDENTIFIER}.zip").write_bytes(b"new builder output")
    github = FakeGitHub(bodies, inventory, existing=True)
    assert publish(github, snapshot) == "verified_existing"
    assert not any(path == "command" or options.get("method") for path, options in github.events)


def test_corrupt_uploaded_bytes_do_not_publish_draft(snapshot):
    _, inventory, bodies = snapshot
    github = FakeGitHub(bodies, inventory)
    github.corrupt_download = True
    with pytest.raises(publication.PublicationError, match="Downloaded release asset mismatch"):
        publish(github, snapshot)
    assert github.release["draft"] is True


def test_missing_or_changed_published_asset_blocks_deployment(snapshot):
    _, inventory, bodies = snapshot
    for mode in ("missing", "changed"):
        github = FakeGitHub(bodies, inventory, existing=True)
        if mode == "missing":
            github.assets.pop()
        else:
            github.assets[0]["digest"] = "sha256:" + "0" * 64
        with pytest.raises(publication.PublicationError):
            publish(github, snapshot)
        assert not any(path == "command" or options.get("method") for path, options in github.events)


def test_partial_draft_resumes_without_replacing_existing_assets(snapshot):
    _, inventory, bodies = snapshot
    github = FakeGitHub(bodies, inventory, existing=True, draft=True)
    retained = github.assets.pop()
    assert publish(github, snapshot) == "published_and_verified"
    upload = next(options for path, options in github.events if path == "command")
    assert [Path(name).name for name in upload[3:upload.index("--repo")]] == [retained["name"]]


def test_empty_upload_placeholder_is_recovered_only_in_matching_draft(snapshot):
    _, inventory, bodies = snapshot
    github = FakeGitHub(bodies, inventory, existing=True, draft=True)
    placeholder = github.assets[-1]
    placeholder.update(state="starter", size=0, digest=None)
    assert publish(github, snapshot) == "published_and_verified"
    assert any(path == f"releases/assets/{placeholder['id']}" and options.get("method") == "DELETE"
               for path, options in github.events)
    github = FakeGitHub(bodies, inventory, existing=True)
    github.assets[-1].update(state="starter", size=0, digest=None)
    with pytest.raises(publication.PublicationError):
        publish(github, snapshot)
    assert not any(options.get("method") == "DELETE" for _, options in github.events)


def test_public_download_verification_is_anonymous_and_checks_body(snapshot, monkeypatch):
    _, inventory, bodies = snapshot
    requests = []
    class Response:
        status = 200
        def __init__(self, request):
            self.request = request
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, _limit): return bodies[self.request.full_url.rsplit("/", 1)[1]]
    def open_url(request, timeout):
        requests.append(request)
        assert not request.has_header("Authorization")
        return Response(request)
    monkeypatch.setattr(publication.urllib.request, "urlopen", open_url)
    publication.verify_public_downloads(inventory, read_bytes=True)
    assert len(requests) == len(bodies)
    bodies["manifest.json"] = b"unexpected public bytes"
    with pytest.raises(publication.PublicationError, match="Public release bytes mismatch"):
        publication.verify_public_downloads(inventory, read_bytes=True)


def test_changed_candidate_and_wrong_commit_leave_remote_state_untouched(snapshot):
    root, inventory, bodies = snapshot
    github = FakeGitHub(bodies, inventory)
    github.tag_commit = "b" * 40
    with pytest.raises(publication.PublicationError, match="tag belongs"):
        publish(github, snapshot)
    assert github.release is None
    github.tag_commit = None
    (root / IDENTIFIER / "manifest.json").write_bytes(b"different")
    with pytest.raises(publication.PublicationError, match="Staged asset differs"):
        publish(github, snapshot)
    assert github.release is None


def test_inventory_rejects_unsafe_urls_duplicates_and_manifest_mismatch(snapshot):
    _, inventory, _ = snapshot
    publication.checked_inventory(inventory, REPO)
    for mutation in ("url", "duplicate", "manifest"):
        value = copy.deepcopy(inventory)
        if mutation == "url":
            value["files"][0]["url"] = "https://example.net/file"
        elif mutation == "duplicate":
            value["files"].append(value["files"][0])
        else:
            value["manifest_sha256"] = "0" * 64
        with pytest.raises(publication.PublicationError):
            publication.checked_inventory(value, REPO)


def test_size_guard_counts_archive_overhead_and_rejects_symlinks(tmp_path):
    (tmp_path / "index.html").write_bytes(b"x" * 512)
    result = check_pages_size.measure(tmp_path)
    assert result["file_bytes"] == 512
    assert result["gnu_tar_bytes_upper_bound"] > result["file_bytes"]
    (tmp_path / "link").symlink_to(tmp_path / "index.html")
    with pytest.raises(ValueError, match="regular files"):
        check_pages_size.measure(tmp_path)


# --------------------------------------------------------------------------------------------
# Legacy releases: sealed from existing assets, then only verified before each deployment

LEGACY = "2026-10-14-research-ninth"


def _zip(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in sorted(members.items()):
            archive.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), body)
    return buffer.getvalue()


def _legacy_release(zip_members=None):
    """A frozen legacy directory: originals, derived files, its zip and SHA256SUMS."""
    sites = b"site_id\nvcc-site-1\n"
    manifest = json.dumps({"files": {"sites.csv": {"bytes": len(sites), "sha256": publication.sha256(sites)}}}).encode()
    directory = {
        "manifest.json": manifest,
        "manifest.sha256": publication.sha256(manifest).encode() + b"  manifest.json\n",
        "sites.csv": sites,
        "atlas.json": b'{"frozen": true}\n',
        "sites.ndjson": b'{"site_id": "vcc-site-1"}\n',
    }
    zip_name = f"datacenter-atlas-{LEGACY}.zip"
    directory[zip_name] = _zip(zip_members if zip_members is not None else directory)
    directory["SHA256SUMS"] = "".join(f"{publication.sha256(body)}  {name}\n"
                                      for name, body in sorted(directory.items())).encode()
    released = ("SHA256SUMS", zip_name, "atlas.json", "sites.csv")
    assets = [{"id": 30 + i, "name": name, "state": "uploaded", "size": len(directory[name]),
               "digest": "sha256:" + publication.sha256(directory[name]),
               "browser_download_url": f"{REPO}/releases/download/data-{LEGACY}/{name}"}
              for i, name in enumerate(released)]
    originals = {name: publication.sha256(directory[name]) for name in ("manifest.json", "manifest.sha256", "sites.csv")}
    return directory, assets, originals


def _rebuilt(directory):
    """The site builder's digests: sites.ndjson as frozen, atlas.json rebuilt differently."""
    return {"atlas.json": publication.sha256(b'{"rebuilt": true}\n'),
            "sites.ndjson": publication.sha256(directory["sites.ndjson"])}


def _seal(directory, assets, originals, rebuilt=None):
    return sealing.legacy_inventory(dataset_id=LEGACY, repository_url=REPO, manifest_sha256=originals["manifest.json"],
                                    originals=originals, assets=assets,
                                    bodies={asset["name"]: directory[asset["name"]] for asset in assets},
                                    rebuilt=_rebuilt(directory) if rebuilt is None else rebuilt)


class LegacyGitHub(FakeGitHub):
    def __init__(self, directory, assets, inventory):
        super().__init__({asset["name"]: directory[asset["name"]] for asset in assets}, inventory, existing=True)
        self.bodies["manifest.json"] = directory["manifest.json"]
        self.release["tag_name"] = inventory["release_tag"]
        self.assets = copy.deepcopy(assets)


def test_seal_records_exact_release_assets_and_its_checksums():
    directory, assets, originals = _legacy_release()
    inventory = _seal(directory, assets, originals)
    assert inventory["schema"] == "datacenter-atlas-legacy-release-assets-v1"
    assert [item["name"] for item in inventory["files"]] == sorted(asset["name"] for asset in assets)
    assert {item["name"]: item["sha256"] for item in inventory["sha256sums"]} == {
        name: publication.sha256(body) for name, body in directory.items() if name != "SHA256SUMS"}
    assert sealing.sha256sums_bytes(inventory["sha256sums"]) == directory["SHA256SUMS"]
    assert publication.checked_legacy_inventory(inventory, REPO) == inventory["files"]
    # Only derived formats the builder still writes byte for byte stay at their local URLs.
    assert inventory["local_files"] == ["sites.ndjson"]
    assert _seal(directory, assets, originals, rebuilt={})["local_files"] == []
    with pytest.raises(sealing.SealError, match="not derived formats"):
        _seal(directory, assets, originals, rebuilt={"sites.csv": publication.sha256(directory["sites.csv"])})


def test_seal_rejects_inconsistent_releases():
    directory, assets, originals = _legacy_release()
    zip_name = f"datacenter-atlas-{LEGACY}.zip"
    members = {name: body for name, body in directory.items() if name not in ("SHA256SUMS", zip_name)}
    cases = {
        "member sites.ndjson differs": _legacy_release(zip_members={**members, "sites.ndjson": b"different"}),
        "members differ": _legacy_release(zip_members={**members, "extra.txt": b"x"}),
        "GitHub's digest": (directory, [{**assets[2], "digest": "sha256:" + "0" * 64}, *assets[:2], assets[3]], originals),
        "original sites.csv": (directory, assets, {**originals, "sites.csv": "0" * 64}),
        f"no {zip_name}": (directory, [asset for asset in assets if asset["name"] != zip_name], originals),
        "unexpected download URL": (directory, [{**assets[0], "browser_download_url": "https://example.net/x"},
                                                *assets[1:]], originals),
    }
    for message, (body, items, known) in cases.items():
        with pytest.raises(sealing.SealError, match=message):
            _seal(body, items, known)
    def reuploaded(body):
        return [{**asset, "size": len(body[asset["name"]]), "digest": "sha256:" + publication.sha256(body[asset["name"]])}
                for asset in assets]

    unsorted = dict(directory)
    unsorted["SHA256SUMS"] = b"".join(sorted(directory["SHA256SUMS"].splitlines(keepends=True), reverse=True))
    with pytest.raises(sealing.SealError, match="sorted"):
        _seal(unsorted, reuploaded(unsorted), originals)
    changed = dict(directory)
    changed["atlas.json"] = b"rebuilt by a newer builder"
    with pytest.raises(sealing.SealError, match="differs from the release's SHA256SUMS"):
        _seal(changed, reuploaded(changed), originals)


def test_seal_reads_a_published_release_and_never_overwrites(tmp_path):
    directory, assets, originals = _legacy_release()
    inventory = _seal(directory, assets, originals)
    dataset = tmp_path / "versions" / LEGACY
    dataset.mkdir(parents=True)
    for name in originals:
        (dataset / name).write_bytes(directory[name])
    github = LegacyGitHub(directory, assets, inventory)
    output = tmp_path / "inventories" / f"{LEGACY}.json"
    asked = []

    def rebuilt(root, dataset_id):
        asked.append((root, dataset_id))
        return _rebuilt(directory)

    written = sealing.seal(github, dataset_id=LEGACY, repository_url=REPO, versions_root="versions",
                           root=tmp_path, output=output, rebuilt=rebuilt)
    assert written == inventory == json.loads(output.read_text())
    assert asked == [(tmp_path, LEGACY)]
    assert not any(options.get("method") or path == "command" for path, options in github.events)
    with pytest.raises(sealing.SealError, match="never replaced"):
        sealing.seal(github, dataset_id=LEGACY, repository_url=REPO, versions_root="versions",
                     root=tmp_path, output=output, rebuilt=rebuilt)
    github.release["draft"] = True
    with pytest.raises(sealing.SealError, match="not a published release"):
        sealing.seal(github, dataset_id=LEGACY, repository_url=REPO, versions_root="versions",
                     root=tmp_path, output=tmp_path / "other.json", rebuilt=rebuilt)


def test_legacy_release_is_only_verified_before_deployment():
    directory, assets, originals = _legacy_release()
    inventory = _seal(directory, assets, originals)
    github = LegacyGitHub(directory, assets, inventory)
    checks = []
    result = publication.verify_legacy_inventory(
        github, inventory, versions_root="verified_construction_core",
        public_verify=lambda value, *, read_bytes: checks.append((value, read_bytes)))
    assert result == "verified_legacy"
    assert checks == [(inventory, False)]
    assert not any(options.get("method") or path == "command" for path, options in github.events)


def test_missing_draft_changed_or_extra_legacy_assets_block_deployment():
    directory, assets, originals = _legacy_release()
    inventory = _seal(directory, assets, originals)
    for mode in ("absent", "draft", "missing", "extra", "changed"):
        github = LegacyGitHub(directory, assets, inventory)
        if mode == "absent":
            github.release = None
        elif mode == "draft":
            github.release["draft"] = True
        elif mode == "missing":
            github.assets.pop()
        elif mode == "extra":
            github.assets.append({**github.assets[0], "id": 99, "name": "sites.kml"})
        else:
            github.assets[1]["digest"] = "sha256:" + "0" * 64
        with pytest.raises(publication.PublicationError):
            publication.verify_legacy_inventory(github, inventory, versions_root="verified_construction_core",
                                                public_verify=lambda *args, **kwargs: None)
        assert not any(options.get("method") or path == "command" for path, options in github.events), mode


def test_legacy_inventory_rejects_tampering():
    directory, assets, originals = _legacy_release()
    inventory = _seal(directory, assets, originals)
    for mutation in ("checksum", "url", "schema", "unsorted"):
        value = copy.deepcopy(inventory)
        if mutation == "checksum":
            value["sha256sums"][0]["sha256"] = "0" * 64
        elif mutation == "url":
            value["files"][0]["url"] = "https://example.net/SHA256SUMS"
        elif mutation == "schema":
            value["schema"] = "datacenter-atlas-release-assets-v1"
        else:
            value["sha256sums"].reverse()
        with pytest.raises(publication.PublicationError):
            publication.checked_legacy_inventory(value, REPO)


def test_a_broken_legacy_release_blocks_deployment_before_any_release_is_written(tmp_path, monkeypatch, capsys):
    directory, assets, originals = _legacy_release()
    legacy = _seal(directory, assets, originals)
    remote = {"schema": "datacenter-atlas-release-assets-v1", "dataset_id": IDENTIFIER, "repository_url": REPO,
              "release_tag": f"data-{IDENTIFIER}", "manifest_sha256": "1" * 64,
              "files": [{"name": name, "bytes": 1, "sha256": "1" * 64,
                         "url": f"{REPO}/releases/download/data-{IDENTIFIER}/{name}"}
                        for name in sorted(["SHA256SUMS", f"datacenter-atlas-{IDENTIFIER}.zip",
                                            "manifest.json", "manifest.sha256"])]}
    (tmp_path / "site/api/v1").mkdir(parents=True)
    (tmp_path / "site/api/v1/index.json").write_text(json.dumps({
        "repository_url": REPO,
        "dataset": {"id": IDENTIFIER, "repository_path": f"verified_construction_core/{IDENTIFIER}"}}))
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/publication.json").write_text(json.dumps({
        "schema": "datacenter-atlas-release-publication-v1", "current_dataset": IDENTIFIER,
        "repository_url": REPO, "inventories": [remote], "legacy_inventories": [legacy]}))
    calls = []

    def broken(github, inventory, *, versions_root):
        calls.append(("verify_legacy", inventory["release_tag"], versions_root))
        raise publication.PublicationError(f"Legacy release asset changed: {inventory['release_tag']}")

    monkeypatch.setenv("GITHUB_REPOSITORY", "example/atlas")
    monkeypatch.setattr(publication, "GitHub", lambda repository: object())
    monkeypatch.setattr(publication, "verify_legacy_inventory", broken)
    monkeypatch.setattr(publication, "publish_inventory", lambda *args, **kwargs: calls.append(("publish",)))
    arguments = ["--site", str(tmp_path / "site"), "--release-assets", str(tmp_path / "assets"),
                 "--commit", COMMIT, "--enabled", "true"]
    assert publication.main(arguments) == 1
    assert calls == [("verify_legacy", f"data-{LEGACY}", "verified_construction_core")]
    assert "Legacy release asset changed" in capsys.readouterr().err


def test_legacy_inventories_require_releases_enabled(tmp_path, capsys):
    directory, assets, originals = _legacy_release()
    inventory = _seal(directory, assets, originals)
    (tmp_path / "site/api/v1").mkdir(parents=True)
    (tmp_path / "site/api/v1/index.json").write_text(json.dumps(
        {"repository_url": REPO, "dataset": {"id": "2026-10-15-research"}}))
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/publication.json").write_text(json.dumps({
        "schema": "datacenter-atlas-release-publication-v1", "current_dataset": "2026-10-15-research",
        "repository_url": REPO, "inventories": [], "legacy_inventories": [inventory]}))
    arguments = ["--site", str(tmp_path / "site"), "--release-assets", str(tmp_path / "assets"),
                 "--commit", COMMIT]
    assert publication.main([*arguments, "--enabled", "false"]) == 1
    assert "require ATLAS_GITHUB_RELEASES=true" in capsys.readouterr().err
