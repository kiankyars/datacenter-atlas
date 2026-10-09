"""Unit tests for the CI helpers next to this file (no browser and no built site needed).

- ``pages_server.py``: serves a directory with GitHub Pages' rules;
- ``check_public_metadata.py``: keeps README.md, CITATION.cff and DATA_LICENSE.md in step with a build;
- ``live_checks.py``: checks the deployed site and classifies evidence links;
- ``release_notes.py``: prepares the GitHub Release of a dataset version.

Run with ``python -m pytest site/e2e/test_ci_scripts.py``; CI runs them with the browser tests.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import threading
import urllib.error
import urllib.request

import pytest

E2E_DIR = Path(__file__).resolve().parent


def _load(name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, E2E_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pages_server = _load("pages_server")
check_public_metadata = _load("check_public_metadata")
live_checks = _load("live_checks")
release_notes = _load("release_notes")

BASE = "https://example.org/atlas/"
DATASET_ID = "2026-08-20-v0.18-draft-thirty-sixth-reviewed"
PREVIEW_ID = "2026-08-20-preview-v0.17"


# --------------------------------------------------------------------------------------------
# pages_server.py


@pytest.fixture
def served(tmp_path):
    site = tmp_path / "site"
    (site / "api" / "v1" / "sites").mkdir(parents=True)
    (site / "api" / "v1" / "index.json").write_text('{"ok": true}\n', encoding="utf-8")
    (site / "api" / "v1" / "sites" / "a.json").write_text("{}\n", encoding="utf-8")
    (site / "index.html").write_text("<h1>home</h1>", encoding="utf-8")
    (site / "about.html").write_text("<h1>about</h1>", encoding="utf-8")
    (site / "404.html").write_text("<h1>custom 404</h1>", encoding="utf-8")
    (site / "data.geojson").write_text("{}", encoding="utf-8")
    server = pages_server.make_server(site, port=0, sub_path="/atlas/")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield pages_server.base_url(server, "/atlas/")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _get(url: str, *, follow: bool = True):
    handlers = [urllib.request.ProxyHandler({})] + ([] if follow else [_NoRedirect()])
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(url, timeout=10) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read()


def test_pages_server_serves_directory_indexes_but_never_listings(served):
    status, headers, body = _get(served)
    assert (status, body) == (200, b"<h1>home</h1>")
    assert headers["Content-Type"].startswith("text/html")
    status, headers, body = _get(served + "api/v1/")
    assert (status, json.loads(body)) == (200, {"ok": True})
    assert headers["Content-Type"].startswith("application/json")
    status, _, body = _get(served + "api/v1/sites/")
    assert status == 404 and body == b"<h1>custom 404</h1>"


def test_pages_server_mirrors_github_pages_details(served):
    status, headers, _ = _get(served + "api/v1", follow=False)
    assert status == 301 and headers["Location"].endswith("/atlas/api/v1/")
    assert _get(served + "about")[2] == b"<h1>about</h1>"
    status, headers, _ = _get(served + "data.geojson")
    assert status == 200 and headers["Content-Type"] == "application/geo+json"
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert _get(served + "index.html/")[0] == 404
    assert _get(served + "missing.json")[0] == 404
    assert _get(served + "../404.html")[0] in (400, 404)
    root = served.split("/atlas/")[0] + "/"
    status, _, body = _get(root + "index.html")
    assert status == 404 and b"custom" not in body, "paths outside the sub-path are not part of the site"


def test_normalize_sub_path():
    assert pages_server.normalize_sub_path("datacenter-atlas") == "/datacenter-atlas/"
    assert pages_server.normalize_sub_path("/a/b") == "/a/b/"
    assert pages_server.normalize_sub_path("/") == "/"


# --------------------------------------------------------------------------------------------
# check_public_metadata.py


def _facts(**changes):
    counts = {
        "physical_sites": 4, "projects": 5, "countries": 3, "evidence": 9, "non_us_sites": 2,
        "official_boundary_projects": 1, "polygon_sites": 1, "point_sites": 3, "power_observation_projects": 1,
    }
    dataset = {
        "id": DATASET_ID,
        "label": "v0.18 draft — thirty-sixth reviewed checkpoint",
        "release_status": "draft",
        "publishable_as_final": False,
        "checkpoint_date": "2026-10-02",
        "lifecycle_reference_date": "2026-08-20",
        "status_window_days": 90,
        "window_start": "2026-05-22",
        "counts": counts,
        "repository_path": f"verified_construction_core/{DATASET_ID}",
    }
    gates = {
        "site_count": {"actual": 4, "passed": False, "required": 200},
        "country_count": {"actual": 3, "passed": False, "required_minimum": 40},
        "maximum_single_country_share": {"actual": 0.5, "passed": False, "required_maximum": 0.4},
        "blind_review": {"agreements": 0, "passed": False, "required_agreements": 19,
                         "required_sample_size": 20, "sample_size": 0},
        "publication_authorized": {"passed": False},
        "imagery_outcomes_complete": {"actual": 1, "passed": False, "required": 5},
    }
    projects = [
        {"project_id": f"p{i}", "site_id": f"s{min(i, 3)}", "geometry_evidence_id": "e-osm" if i < 2 else "e1",
         "power_observations": [{}, {}] if i == 0 else [], "role_claims": [], "workloads": [],
         "operating_model": "unknown", "horizontal_uncertainty_metres": None,
         "imagery_review_outcome": "not_reviewed_for_core_preview"}
        for i in range(5)
    ]
    documents = {
        "index": {"base_url": BASE, "dataset": dataset},
        "stats": {"release_gates": gates},
        "versions": {"current": DATASET_ID, "last_preview": PREVIEW_ID, "versions": [
            {"id": PREVIEW_ID, "label": "v0.17 preview", "counts": {"physical_sites": 100}},
            {"id": DATASET_ID, "label": dataset["label"], "counts": counts},
        ]},
        "countries": [
            {"country": "United States", "country_iso_a2": "US", "site_count": 2},
            {"country": "Australia", "country_iso_a2": "AU", "site_count": 1},
            {"country": "Germany", "country_iso_a2": "DE", "site_count": 1},
        ],
        "projects": projects,
        "evidence": [{"evidence_id": "e-osm", "license": "ODbL-1.0"}, {"evidence_id": "e1", "license": "x"}],
        "config": {
            "site_name": "Data Center Atlas", "base_url": BASE, "versions_root": "verified_construction_core",
            "repository_url": "https://github.com/example/atlas", "status_window_days": 90,
            "author": {"name": "Kian Kyars", "url": "https://github.com/kiankyars"},
            "data_license": {"id": "CC-BY-4.0"},
        },
    }
    for key, value in changes.items():
        documents[key] = value
    return check_public_metadata.facts_from_documents(**documents)


def _write_repo(root: Path, *, readme_extra: str = "", contributing: str = "") -> Path:
    (root / "README.md").write_text(
        "# Atlas\n\n## Current dataset\n\n<!-- atlas:current-dataset -->\n<!-- /atlas:current-dataset -->\n\n"
        "<!-- atlas:version-files -->\n<!-- /atlas:version-files -->\n\n"
        "## Cite\n\n<!-- atlas:citation -->\n<!-- /atlas:citation -->\n\n" + readme_extra,
        encoding="utf-8",
    )
    (root / "DATA_LICENSE.md").write_text(
        "Example:\n\n<!-- atlas:attribution-example -->\n<!-- /atlas:attribution-example -->\n\n"
        "OSM (<!-- atlas:osm-geometry-count --><!-- /atlas:osm-geometry-count -->).\n",
        encoding="utf-8",
    )
    (root / "CONTRIBUTING.md").write_text(contributing or "Contribute.\n", encoding="utf-8")
    (root / "CITATION.cff").write_text("stale\n", encoding="utf-8")
    return root


def test_metadata_write_then_check_is_clean(tmp_path):
    repo = _write_repo(tmp_path)
    facts = _facts()
    assert check_public_metadata.check(repo, facts), "a fresh repository must be reported as stale"
    changed = check_public_metadata.write(repo, facts)
    assert sorted(changed) == ["CITATION.cff", "DATA_LICENSE.md", "README.md"]
    assert check_public_metadata.check(repo, facts) == []
    assert check_public_metadata.write(repo, facts) == [], "write is idempotent"
    readme = (repo / "README.md").read_text(encoding="utf-8")
    assert f"`{DATASET_ID}`" in readme and "**4 physical sites**" in readme
    assert "| Largest single-country share | at most 40% | 50% (United States) | No |" in readme
    assert "Six of the six final-release gates are not yet met" in readme
    assert "between 2026-05-22 and 2026-08-20 inclusive" in readme
    license_text = (repo / "DATA_LICENSE.md").read_text(encoding="utf-8")
    assert "(<!-- atlas:osm-geometry-count -->2 of the 5 project geometries, on 2 sites, in the 2026-10-02" in license_text
    citation = (repo / "CITATION.cff").read_text(encoding="utf-8")
    assert f'version: "{DATASET_ID}"' in citation and 'date-released: "2026-10-02"' in citation
    assert "ODbL 1.0" in citation and "doi:" not in citation


def test_metadata_names_locator_exceptions(tmp_path):
    projects = copy.deepcopy(_facts().projects)
    projects[4]["name"] = "Digital Edge CGK1"
    projects[4]["geometry_use_scope"] = "host_estate_context"
    facts = _facts(projects=projects)
    repo = _write_repo(tmp_path)
    check_public_metadata.write(repo, facts)
    readme = " ".join((repo / "README.md").read_text(encoding="utf-8").split())
    assert "One project (Digital Edge CGK1) has host-estate context only, not a reviewed locator" in readme
    citation = " ".join((repo / "CITATION.cff").read_text(encoding="utf-8").split())
    assert "(or, for a listed locator exception, host-estate context only)" in citation
    assert check_public_metadata.check(repo, facts) == []
    plain = tmp_path / "plain"
    plain.mkdir()
    check_public_metadata.write(_write_repo(plain), _facts())
    assert "host-estate" not in (plain / "CITATION.cff").read_text(encoding="utf-8")


def test_metadata_reports_a_new_checkpoint_until_rewritten(tmp_path):
    repo = _write_repo(tmp_path)
    check_public_metadata.write(repo, _facts())
    newer = copy.deepcopy(_facts().index)
    newer["dataset"]["id"] = "2026-08-20-v0.18-draft-thirty-seventh-reviewed"
    problems = check_public_metadata.check(repo, _facts(index=newer))
    assert any(problem.startswith("CITATION.cff") for problem in problems)
    assert any("current-dataset block is stale" in problem for problem in problems)


def test_metadata_flags_stale_prose(tmp_path):
    readme = (
        "Coverage: the United States, Australia and Germany hold 3 of the 4 sites. Only 2 projects use an "
        "official site boundary; 3 sites are located by a point and 1 by a polygon. One of the 5 projects "
        "carry one (2 observations). One projects carry an imagery-review outcome.\n\n"
        "python3 scripts/build_expansion_200_draft.py --batch thirty-fifth-reviewed --validate-only\n"
        "python3 -m unittest tests.test_expansion_200_thirty_fifth_reviewed\n"
        "See 2026-08-20-v0.18-draft-thirty-fifth-reviewed.\n"
    )
    repo = _write_repo(tmp_path, readme_extra=readme)
    check_public_metadata.write(repo, _facts())
    problems = check_public_metadata.check(repo, _facts())
    text = "\n".join(problems)
    assert "country coverage" in text and "the build has 4 sites" in text
    assert "official boundaries" in text
    assert "draft builder batch" in text and "thirty-sixth-reviewed" in text
    assert "checkpoint test module" in text and "test_expansion_200_thirty_sixth_reviewed" in text
    assert "dataset version" in text
    for fine in ("point sites", "polygon sites", "power observations", "imagery outcomes", "site total"):
        assert fine not in text, f"{fine} was flagged although it is correct:\n{text}"


def test_metadata_blocks_must_exist_exactly_once(tmp_path):
    repo = _write_repo(tmp_path)
    (repo / "README.md").write_text("no markers\n", encoding="utf-8")
    problems = check_public_metadata.check(repo, _facts())
    assert any("needs exactly one <!-- atlas:current-dataset -->" in problem for problem in problems)
    with pytest.raises(check_public_metadata.MetadataError):
        check_public_metadata.write(repo, _facts())


def test_metadata_wrap_never_breaks_links():
    text = "word " * 15 + "[versions page](https://example.org/versions/) and **197 physical sites** end"
    wrapped = check_public_metadata.wrap(text, width=40)
    assert "[versions page](https://example.org/versions/)" in wrapped
    assert "**197 physical sites**" in wrapped


def test_metadata_matches_this_repository_when_a_site_is_built():
    """The repository's own files agree with a build in _site/ (skipped when there is none)."""
    repo = E2E_DIR.parents[1]
    site = repo / "_site"
    if not (site / "api" / "v1" / "index.json").is_file():
        pytest.skip("no built site in _site/")
    facts = check_public_metadata.load_facts(site, repo)
    assert check_public_metadata.check(repo, facts) == []


# --------------------------------------------------------------------------------------------
# live_checks.py


def _response(url, status=200, body=b"", content_type="application/json", cors=True):
    headers = {"content-type": content_type}
    if cors:
        headers["access-control-allow-origin"] = "*"
    return live_checks.Response(url, status, headers, body)


def _fake_site(commit="abc"):
    sha = hashlib.sha256(b"a,b\n").hexdigest()
    index = {
        "base_url": BASE,
        "build": {"source_commit": commit},
        "endpoints": {
            "index": BASE + "api/v1/index.json",
            "sites": BASE + "api/v1/sites.json",
            "site": BASE + "api/v1/sites/{site_id}.json",
        },
        "downloads": [{"url": BASE + "downloads/latest/sites.csv", "sha256": sha}],
    }
    files = {
        BASE + "api/v1/index.json": json.dumps(index).encode(),
        BASE + "api/v1/sites.json": b'[{"site_id": "vcc-site-1"}]',
        BASE + "api/v1/sites/vcc-site-1.json": b"{}",
        BASE + "downloads/latest/SHA256SUMS": f"{sha}  sites.csv\n".encode(),
        BASE + "downloads/latest/sites.csv": b"a,b\n",
    }
    return index, files


def _fetcher(files, *, broken=()):
    def fetch(url, **_):
        plain = url.split("?", 1)[0]
        if plain in broken:
            return _response(plain, 404)
        if plain in files:
            kind = "application/json" if plain.endswith(".json") else "text/plain"
            return _response(plain, 200, files[plain], kind)
        if plain.endswith("/") or plain.endswith((".xml", ".txt")):
            return _response(plain, 200, b"<html></html>", "text/html")
        return _response(plain, 404)
    return fetch


def test_live_checks_pass_on_a_consistent_site():
    index, files = _fake_site()
    report = live_checks.check_deployment(BASE, index, token="t", fetch=_fetcher(files))
    assert report.problems == []
    assert report.checked >= len(live_checks.PAGES) + 4


def test_live_checks_report_missing_cors_bad_hashes_and_404s():
    index, files = _fake_site()
    files[BASE + "downloads/latest/sites.csv"] = b"tampered\n"
    fetch = _fetcher(files, broken={BASE + "llms.txt"})

    def no_cors(url, **kwargs):
        response = fetch(url, **kwargs)
        if "sites.json" in url:
            response.headers.pop("access-control-allow-origin", None)
        return response

    problems = "\n".join(live_checks.check_deployment(BASE, index, token="t", fetch=no_cors).problems)
    assert "Access-Control-Allow-Origin" in problems
    assert "does not match" in problems
    assert "page llms.txt: HTTP 404" in problems


def test_wait_for_commit_polls_until_the_commit_is_served():
    served = iter(["old", "old", "new"])
    clock = iter(range(100))

    def fetch(url):
        return _response(url, 200, json.dumps({"build": {"source_commit": next(served)}}).encode())

    index = live_checks.wait_for_commit(BASE, "new", timeout=50, fetch=fetch, sleep=lambda _: None,
                                        clock=lambda: next(clock))
    assert index["build"]["source_commit"] == "new"
    with pytest.raises(live_checks.LiveCheckError, match="did not serve commit"):
        live_checks.wait_for_commit(BASE, "never", timeout=2, fetch=lambda url: _response(url, 503),
                                    sleep=lambda _: None, clock=lambda: next(clock))


def test_classify_link():
    def fetch_status(status):
        return lambda url, **_: _response(url, status, b"", "text/html")

    assert live_checks.classify_link("https://a", fetch=fetch_status(200)).outcome == "ok"
    assert live_checks.classify_link("https://a", fetch=fetch_status(410)).outcome == "dead"
    assert live_checks.classify_link("https://a", fetch=fetch_status(403)).outcome == "unverified"

    def unknown_host(url, **_):
        raise urllib.error.URLError(socket.gaierror(8, "nodename nor servname provided"))

    def timeout(url, **_):
        raise TimeoutError("timed out")

    assert live_checks.classify_link("https://a", fetch=unknown_host).outcome == "dead"
    assert live_checks.classify_link("https://a", fetch=timeout).outcome == "unverified"


def test_link_report_groups_evidence_and_fits_an_issue():
    evidence = [
        {"evidence_id": "e1", "source_url": "https://dead.example/a", "site_ids": ["vcc-site-1"]},
        {"evidence_id": "e2", "source_url": "https://dead.example/a", "site_ids": ["vcc-site-2"]},
        {"evidence_id": "e3", "source_url": "ftp://ignored.example/"},
    ] + [{"evidence_id": f"x{i}", "source_url": f"https://slow.example/{i}", "site_ids": []} for i in range(2000)]
    outcomes = {"https://dead.example/a": "dead"}
    results, grouped = live_checks.check_links(
        evidence, delay=0,
        classify=lambda url: live_checks.LinkResult(url, outcomes.get(url, "unverified"), "HTTP 403"),
    )
    assert len(results) == 2001 and "ftp://ignored.example/" not in grouped
    text = live_checks.link_report(BASE, results, grouped, dataset_id=DATASET_ID, checked_on="2026-10-09")
    assert len(text) <= live_checks.MAX_REPORT_CHARS
    assert "### Dead" in text and "`e1`, `e2`" in text
    assert f"[vcc-site-1]({BASE}sites/vcc-site-1/)" in text
    assert "more |" in text


# --------------------------------------------------------------------------------------------
# release_notes.py


def test_release_notes_and_assets(tmp_path):
    site = tmp_path / "site"
    directory = site / "downloads" / DATASET_ID
    directory.mkdir(parents=True)
    for name in (f"datacenter-atlas-{DATASET_ID}.zip", "SHA256SUMS", "sites.csv", "atlas.sqlite", "README.md"):
        (directory / name).write_bytes(b"x")
    paths = release_notes.asset_paths(site, DATASET_ID)
    assert [path.name for path in paths] == [f"datacenter-atlas-{DATASET_ID}.zip", "SHA256SUMS", "sites.csv", "atlas.sqlite"]
    index = {
        "base_url": BASE,
        "repository_url": "https://github.com/example/atlas",
        "dataset": _facts().index["dataset"],
    }
    versions = {"versions": [{"id": DATASET_ID, "added_site_ids": ["vcc-site-1", "vcc-site-9"], "removed_site_ids": []}]}
    sites = [{"site_id": "vcc-site-1", "name": "Alpha <campus>", "country": "Chile"}]
    text = release_notes.notes(index, versions, sites, commit="abc123", citation={"apa": "Kyars, K. (2026). X."})
    assert f"Dataset version `{DATASET_ID}`" in text
    assert "not a final release" in text
    assert f"[Alpha \\<campus\\>]({BASE}sites/vcc-site-1/) (Chile)" in text and "- `vcc-site-9`" in text
    assert "Cite as: Kyars, K. (2026). X." in text
    assert "last observed physical status" in text and "not a census" in text
    assert "Built from commit abc123." in text
    assert release_notes.release_tag(DATASET_ID) == f"data-{DATASET_ID}"


def test_release_notes_require_the_version_zip(tmp_path):
    (tmp_path / "downloads" / DATASET_ID).mkdir(parents=True)
    with pytest.raises(release_notes.ReleaseError, match="has no datacenter-atlas"):
        release_notes.asset_paths(tmp_path, DATASET_ID)
