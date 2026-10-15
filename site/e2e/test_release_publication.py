"""Offline tests for publication order, frozen assets, and failed-run recovery."""

import copy
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import publish_release as publication
import check_pages_size

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
