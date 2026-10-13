"""Browser end-to-end tests for the built public site.

CI (``.github/workflows/pages.yml``) builds the site, serves a copy under the ``/datacenter-atlas/``
sub-path (as GitHub Pages does) and runs, from the directory that contains the checkout::

    ATLAS_BASE_URL=http://127.0.0.1:8000/datacenter-atlas/ ATLAS_E2E_REQUIRED=1 \\
        python -m pytest datacenter_atlas/site/e2e -q

Locally, after
``python -m pip install --require-hashes --only-binary :all: -r site/e2e/requirements.txt`` and
``python -m playwright install chromium``, ``python -m pytest site/e2e`` serves ``_site/`` (or
``$ATLAS_SITE_DIR``) itself under the same sub-path on an ephemeral 127.0.0.1 port. Both servers
are ``pages_server.py``, which follows GitHub Pages' rules (a directory URL answers with its
``index.html`` or ``index.json`` and never with a listing; a missing path gets ``404.html`` with
status 404), so a URL that passes here also works in production. Without Playwright the browser
tests skip (the API, download and metadata checks still run when a built site is available);
``ATLAS_E2E_REQUIRED=1`` turns every skip into an error.

The tests are hermetic: every request to a host other than the local server is answered with a
transparent 1x1 PNG (images) or aborted (everything else). The site promises no third-party
requests except basemap tiles, so any other external request is also recorded and fails the test.
Expected numbers are read from the built ``api/v1/*.json`` files, never hard-coded. Screenshots are
written to ``$ATLAS_SCREENSHOT_DIR`` (default ``site-screenshots/`` in the working directory).
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import struct
import sys
import threading
import time
import unicodedata
import urllib.error
from urllib.parse import parse_qs, quote, urldefrag, urljoin, urlsplit
import urllib.request
import warnings
import zlib

import pytest

try:  # Only the browser tests need Playwright; without it they skip (see the chromium fixture).
    from playwright.sync_api import expect, sync_playwright
except ModuleNotFoundError:
    if os.environ.get("ATLAS_E2E_REQUIRED") == "1":
        raise
    expect = sync_playwright = None


REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_DIR = Path(__file__).resolve().parent
SUB_PATH = "/datacenter-atlas/"


def _load_sibling(name: str):
    """Import a helper module that sits next to this file, whatever pytest's import mode."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, E2E_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


pages_server = _load_sibling("pages_server")
check_public_metadata = _load_sibling("check_public_metadata")

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "tablet": {"width": 820, "height": 1180},
    "phone": {"width": 390, "height": 844},
}
NARROW_VIEWPORT = {"width": 360, "height": 780}
WIDE_LAYOUT_MIN_WIDTH = 1024
DEFAULT_TIMEOUT_MS = 15_000
NAVIGATION_TIMEOUT_MS = 30_000
READY_TIMEOUT_MS = 30_000
POLYGON_TYPES = ("Polygon", "MultiPolygon")
# Hosts the site may contact (spec: no third-party requests except basemap tiles).
TILE_HOSTS = (
    re.compile(r"(?:^|\.)basemaps\.cartocdn\.com$"),
    re.compile(r"^tile\.openstreetmap\.org$"),
    re.compile(r"^tiles\.maps\.eox\.at$"),
)
# Columns every explorer CSV export must have (it may have more; see _expected_export_columns).
EXPORT_CSV_REQUIRED_COLUMNS = (
    "site_id", "name", "country", "country_iso_a2", "latitude", "longitude", "url", "dataset_id",
)
STATIC_PAGES = (
    "sites/",
    "countries/",
    "data/",
    "data/dictionary/",
    "api/",
    "methodology/",
    "versions/",
    "about/",
    "about/attribution/",
    "downloads/",
    "downloads/latest/",
)
# Leaflet-generated markup is third-party; the accessibility check covers our own markup.
AXE_CONTEXT = {"exclude": [".leaflet-pane", ".leaflet-control-container"]}

if expect is not None:
    expect.set_options(timeout=DEFAULT_TIMEOUT_MS)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


TRANSPARENT_PNG = (
    b"\x89PNG\r\n\x1a\n"
    + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    + _png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))
    + _png_chunk(b"IEND", b"")
)

# Unique ids of list rows that are rendered and not hidden, in document order.
VISIBLE_ROW_IDS_JS = """() => {
  const list = document.getElementById('atlas-list');
  if (!list) return null;
  const ids = [];
  const seen = new Set();
  for (const el of list.querySelectorAll('[data-site-id]')) {
    if (!el.getClientRects().length || getComputedStyle(el).visibility === 'hidden') continue;
    const id = el.getAttribute('data-site-id');
    if (!seen.has(id)) { seen.add(id); ids.push(id); }
  }
  return ids;
}"""
FOCUSED_ROW_JS = """() => {
  const el = document.activeElement;
  const row = el && el.closest ? el.closest('#atlas-list [data-site-id]') : null;
  return row ? row.getAttribute('data-site-id') : null;
}"""
DRAWN_PATHS_JS = """(els) => els.filter((el) => {
  const d = (el.getAttribute('d') || '').trim();
  return d !== '' && d !== 'M0 0';
}).length"""
# Text of the explorer outside the list, map, drawer and form controls (the summary strip etc.).
EXPLORER_SUMMARY_TEXT_JS = """() => {
  const clone = document.body.cloneNode(true);
  const skipped = ['#atlas-list', '#atlas-map', '#atlas-detail', 'select', 'noscript', 'script'];
  for (const selector of skipped) {
    clone.querySelectorAll(selector).forEach((node) => node.remove());
  }
  return clone.textContent;
}"""
VISIBLE_TABLE_ROWS_JS = """(table) => Array.from(table.querySelectorAll('tr'))
  .filter((row) => row.querySelector('td') && row.getClientRects().length)
  .map((row) => Array.from(row.cells, (cell) => cell.textContent.trim()))"""
OVERFLOW_JS = """() => {
  const root = document.documentElement;
  const viewport = root.clientWidth;
  const width = root.scrollWidth;
  const offenders = [];
  if (width > viewport + 1) {
    const describe = (el) => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
      (typeof el.className === 'string' && el.className.trim()
        ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
    for (const el of document.querySelectorAll('body *')) {
      const rect = el.getBoundingClientRect();
      if (!rect.width || rect.right <= viewport + 1) continue;
      let clipped = false;
      for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
        if (getComputedStyle(a).overflowX !== 'visible') { clipped = true; break; }
      }
      if (!clipped) offenders.push(describe(el) + ' right=' + Math.round(rect.right));
      if (offenders.length >= 8) break;
    }
  }
  return { viewport, width, offenders };
}"""
HREFS_JS = "(els) => els.map((el) => el.getAttribute('href'))"
# Evidence links are compared in the browser's own URL serialisation on both sides: the explorer
# assigns normalised URLs (lower-case host, percent-encoding), the raw source_url may not be.
LINK_URLS_JS = "(els) => els.map((el) => el.href)"
NORMALIZE_URLS_JS = """(urls) => urls.map((url) => {
  try { return new URL(url).href; } catch (error) { return url; }
})"""
# Every text node (one per line, so a URL never runs into a neighbouring button label) plus every
# copy-button payload: snippets, prose and JSON-LD carry absolute URLs.
SNIPPET_TEXT_JS = """() => {
  const parts = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) parts.push(node.nodeValue);
  for (const el of document.querySelectorAll('[data-copy]')) {
    parts.push(el.getAttribute('data-copy'));
  }
  return parts.join('\\n');
}"""


# Centres of the drawn site markers and the map's box, in viewport pixels.
MARKER_GEOMETRY_JS = """() => {
  const map = document.getElementById('atlas-map');
  if (!map || !map.getClientRects().length) return null;
  const box = map.getBoundingClientRect();
  const markers = [];
  for (const el of map.querySelectorAll('path.atlas-marker')) {
    const d = (el.getAttribute('d') || '').trim();
    if (!d || d === 'M0 0' || !el.getClientRects().length) continue;
    const style = getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') continue;
    const r = el.getBoundingClientRect();
    markers.push([Math.round((r.left + r.right) / 2), Math.round((r.top + r.bottom) / 2)]);
  }
  markers.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  return {
    box: [Math.round(box.left), Math.round(box.top), Math.round(box.right), Math.round(box.bottom)],
    markers,
    animating: !!map.querySelector('.leaflet-zoom-anim, .leaflet-pan-anim'),
  };
}"""
FOCUS_IN_DETAIL_JS = """() => {
  const detail = document.getElementById('atlas-detail');
  const el = document.activeElement;
  if (!detail || !el) return [false, 'nothing'];
  const label = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
    (el.textContent ? ' "' + el.textContent.trim().slice(0, 40) + '"' : '');
  return [detail.contains(el), label];
}"""
FIRST_COLUMN_WIDTHS_JS = """() => Array.from(document.querySelectorAll('table.data-table tbody td:first-child'))
  .filter((cell) => cell.getClientRects().length)
  .map((cell) => [Math.round(cell.getBoundingClientRect().width), cell.textContent.trim().slice(0, 40)])"""
# WebMCP stand-ins installed before any page script runs. The browser under test does not need to
# support WebMCP: these cover "absent", "broken" and a recorder that captures what the page registers.
WEBMCP_STUBS = {
    "absent": "undefined",
    "throws": "{ registerTool() { throw new Error('WebMCP stub: registration refused'); } }",
    "rejects": "{ registerTool() { return Promise.reject(new Error('WebMCP stub: registration refused')); } }",
}
WEBMCP_INSTALL_JS = """(() => {
  const context = %s;
  for (const target of [document, navigator]) {
    try { Object.defineProperty(target, 'modelContext', { value: context, configurable: true }); } catch (e) {}
  }
})();"""
WEBMCP_RECORDER_JS = """(() => {
  const calls = [];
  const unregistered = [];
  const context = {
    registerTool(tool, options) { calls.push({ tool, signal: options && options.signal }); return Promise.resolve(); },
    unregisterTool(name) { unregistered.push(String(name)); },
    provideContext() {},
    clearContext() {},
  };
  Object.defineProperty(window, '__atlasWebmcp', { value: { calls, unregistered } });
  for (const target of [document, navigator]) {
    try { Object.defineProperty(target, 'modelContext', { value: context, configurable: true }); } catch (e) {}
  }
})();"""
WEBMCP_TOOLS_JS = """() => window.__atlasWebmcp.calls.map(({ tool }) => ({
  name: tool && tool.name,
  description: tool && tool.description,
  annotations: (tool && tool.annotations) || {},
  schemaType: tool && tool.inputSchema && tool.inputSchema.type,
  executable: typeof (tool && tool.execute) === 'function',
}))"""
WEBMCP_EXECUTE_JS = """async ([name, input]) => {
  const call = window.__atlasWebmcp.calls.find(({ tool }) => tool && tool.name === name);
  if (!call) return { error: 'not registered' };
  try {
    const result = await call.tool.execute(input, { requestUserInteraction: async (callback) => callback() });
    return { result: JSON.stringify(result === undefined ? null : result) };
  } catch (error) {
    return { error: String((error && error.message) || error) };
  }
}"""
WEBMCP_TOOL_NAMES = ("search_datacenter_sites", "get_datacenter_site", "get_datacenter_dataset_info")


# --------------------------------------------------------------------------------------------
# The site under test


_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _http_get(url: str, *, timeout: float = 60.0) -> bytes:
    return _http_fetch(url, timeout=timeout)[1]


def _http_fetch(url: str, *, timeout: float = 60.0) -> tuple[dict[str, str], bytes]:
    """(lower-cased headers, body) of a 200 response; any other status fails the test."""
    request = urllib.request.Request(url, headers={"User-Agent": "datacenter-atlas-e2e"})
    try:
        with _NO_PROXY_OPENER.open(request, timeout=timeout) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            return headers, response.read()
    except urllib.error.HTTPError as error:
        raise AssertionError(f"GET {url} -> HTTP {error.code}") from None


def _http_status(url: str, *, timeout: float = 60.0) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "datacenter-atlas-e2e"})
    try:
        with _NO_PROXY_OPENER.open(request, timeout=timeout) as response:
            response.read()
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


class _LocalSite:
    """A built ``_site`` on an ephemeral 127.0.0.1 port (used when ATLAS_BASE_URL is unset).

    Served by ``pages_server.py``, as in CI: only under SUB_PATH and with GitHub Pages' rules.
    """

    def __init__(self, directory: Path) -> None:
        self._server = pages_server.make_server(directory, port=0, sub_path=SUB_PATH)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="atlas-e2e-http", daemon=True
        )
        self._thread.start()
        self.base_url = pages_server.base_url(self._server, SUB_PATH)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=10)


class Atlas:
    """The served site plus the API documents every expectation is read from."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        parts = urlsplit(base_url)
        self.origin = f"{parts.scheme}://{parts.netloc}"
        self.host = (parts.hostname or "").lower()
        self.index = self.get_json("api/v1/index.json")
        self.production_base_url = self.index["base_url"]
        self.dataset_id = self.index["dataset"]["id"]
        self.counts = self.index["dataset"]["counts"]
        self.sites = self.get_json(self.index["endpoints"]["sites"])
        self.sites_by_id = {site["site_id"]: site for site in self.sites}
        self.countries = self.get_json(self.index["endpoints"]["countries"])
        self._site_docs: dict[str, dict] = {}

    def url(self, path: str = "") -> str:
        """Local absolute URL of a site-relative path ("" is the explorer)."""
        return urljoin(self.base_url, path)

    def localize(self, url: str) -> str:
        """Map an absolute production URL (as written in the API) onto the local server."""
        if url.startswith(self.base_url):
            return url
        assert url.startswith(self.production_base_url), (
            f"{url!r} is not under the published base URL {self.production_base_url!r}"
        )
        return self.base_url + url[len(self.production_base_url):]

    def get_bytes(self, path_or_url: str) -> bytes:
        url = path_or_url if "://" in path_or_url else self.url(path_or_url)
        return _http_get(self.localize(url))

    def get_json(self, path_or_url: str):
        return json.loads(self.get_bytes(path_or_url).decode("utf-8"))

    def site_doc(self, site_id: str) -> dict:
        if site_id not in self._site_docs:
            template = self.index["endpoints"]["site"]
            self._site_docs[site_id] = self.get_json(template.replace("{site_id}", site_id))
        return self._site_docs[site_id]


class Guard:
    """Keeps a browser context hermetic and records console errors and failed requests."""

    def __init__(self, atlas: Atlas) -> None:
        self._origin = atlas.origin
        self._local_hosts = {"127.0.0.1", atlas.host}
        self.console_errors: list[str] = []
        self.page_errors: list[str] = []
        self.failed_requests: list[str] = []
        self.third_party_requests: list[str] = []

    def handle_route(self, route, request) -> None:
        host = (urlsplit(request.url).hostname or "").lower()
        if host in self._local_hosts:
            route.continue_()
            return
        is_image = request.resource_type == "image"
        if not (is_image and any(pattern.search(host) for pattern in TILE_HOSTS)):
            self.third_party_requests.append(f"{request.resource_type} {request.url}")
        if is_image:
            route.fulfill(
                status=200,
                content_type="image/png",
                body=TRANSPARENT_PNG,
                headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
            )
        else:
            route.abort("blockedbyclient")

    def watch(self, page) -> None:
        page.on("console", self._on_console)
        page.on("pageerror", self._on_page_error)
        page.on("requestfailed", self._on_request_failed)
        page.on("response", self._on_response)

    def _same_origin(self, url: str) -> bool:
        return url == self._origin or url.startswith(self._origin + "/")

    def _on_console(self, message) -> None:
        if message.type == "error":
            location = message.location or {}
            self.console_errors.append(
                f"{message.text} [{location.get('url', '')}:{location.get('lineNumber', '')}]"
            )

    def _on_page_error(self, error) -> None:
        self.page_errors.append(str(error))

    def _on_request_failed(self, request) -> None:
        failure = request.failure or "unknown error"
        # ERR_ABORTED is a request the page itself cancelled (navigation, superseded fetch).
        if self._same_origin(request.url) and "ERR_ABORTED" not in failure:
            self.failed_requests.append(f"{request.method} {request.url}: {failure}")

    def _on_response(self, response) -> None:
        if response.status < 400 or not self._same_origin(response.url):
            return
        if urlsplit(response.url).path == "/favicon.ico":  # browser probe outside the site
            return
        self.failed_requests.append(
            f"{response.request.method} {response.url}: HTTP {response.status}"
        )

    def assert_clean(self) -> None:
        problems = (
            [f"console error: {item}" for item in self.console_errors]
            + [f"uncaught exception: {item}" for item in self.page_errors]
            + [f"failed same-origin request: {item}" for item in self.failed_requests]
            + [
                f"third-party request (only basemap tiles are allowed): {item}"
                for item in self.third_party_requests
            ]
        )
        assert not problems, "\n".join(problems)


def _skip_or_fail(reason: str) -> None:
    if os.environ.get("ATLAS_E2E_REQUIRED") == "1":
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def atlas():
    base_url = os.environ.get("ATLAS_BASE_URL", "").strip()
    local_site = None
    if not base_url:
        site_dir = Path(os.environ.get("ATLAS_SITE_DIR") or REPO_ROOT / "_site")
        if not (site_dir / "api" / "v1" / "index.json").is_file():
            _skip_or_fail(
                f"no built site at {site_dir}; run scripts/build_public_site.py --output _site "
                "or set ATLAS_BASE_URL"
            )
        local_site = _LocalSite(site_dir)
        base_url = local_site.base_url
    if not base_url.endswith("/"):
        base_url += "/"
    try:
        try:
            site = Atlas(base_url)
        except (urllib.error.URLError, OSError) as error:
            pytest.fail(f"cannot read the site API at {base_url}: {error}")
        yield site
    finally:
        if local_site is not None:
            local_site.close()


@pytest.fixture(scope="session")
def chromium():
    pytest.importorskip(
        "playwright", reason="Playwright is not installed; the browser tests run in CI"
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def open_page(chromium, atlas):
    """Factory: a fresh hermetic browser context and page, plus its Guard."""
    contexts = []

    def factory(
        viewport: dict | None = None,
        *,
        javascript: bool = True,
        bypass_csp: bool = False,
        color_scheme: str = "light",
        permissions: tuple[str, ...] = (),
        reduced_motion: str = "reduce",
        init_script: str | None = None,
    ):
        # Most tests ask for reduced motion, so map moves are instant and deterministic;
        # test_auto_fit_follows_consecutive_filters exercises the animated code paths.
        context = chromium.new_context(
            viewport=viewport or VIEWPORTS["desktop"],
            device_scale_factor=1,
            java_script_enabled=javascript,
            bypass_csp=bypass_csp,
            color_scheme=color_scheme,
            reduced_motion=reduced_motion,
            locale="en-US",
            timezone_id="UTC",
            service_workers="block",
        )
        contexts.append(context)
        context.set_default_timeout(DEFAULT_TIMEOUT_MS)
        context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
        if permissions:
            context.grant_permissions(list(permissions), origin=atlas.origin)
        guard = Guard(atlas)
        context.route("**/*", guard.handle_route)
        if init_script:
            context.add_init_script(script=init_script)
        page = context.new_page()
        guard.watch(page)
        return page, guard

    yield factory
    for context in contexts:
        context.close()


@pytest.fixture(scope="session")
def screenshot_dir() -> Path:
    directory = Path(os.environ.get("ATLAS_SCREENSHOT_DIR") or "site-screenshots")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


# --------------------------------------------------------------------------------------------
# Data probes (deterministic choices made from the API, never hard-coded)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").casefold()


# Letters a search may transliterate rather than drop (as the explorer does), and apostrophes it
# may delete, so the search probe's word stays unique under any of those foldings.
_TRANSLITERATION = str.maketrans(
    {
        "\u00df": "ss", "\u00e6": "ae", "\u0153": "oe", "\u00f8": "o",
        "\u0142": "l", "\u0111": "d", "\u00f0": "d", "\u00fe": "th",
        "\u0131": "i", "\u0127": "h", "\u0167": "t", "\u014b": "ng",
    }
)
_APOSTROPHES = re.compile("['\u2019\u02bc`\u00b4]")


def _search_haystack(text: str) -> str:
    lowered = text.casefold()
    variants = {lowered, lowered.translate(_TRANSLITERATION)}
    variants |= {_APOSTROPHES.sub("", variant) for variant in variants}
    return "\n".join(_fold(variant) for variant in sorted(variants))


def _by_name(sites: list[dict]) -> list[dict]:
    return sorted(sites, key=lambda site: (site["name"].casefold(), site["site_id"]))


def _is_http_url(value) -> bool:
    return isinstance(value, str) and urlsplit(value).scheme in ("http", "https")


def _search_probe(atlas: Atlas) -> tuple[dict, str]:
    """A site plus a whole word of its name that occurs in no other site summary at all."""
    haystacks = {
        site["site_id"]: _search_haystack(json.dumps(site, ensure_ascii=False))
        for site in atlas.sites
    }
    for site in _by_name(atlas.sites):
        for word in re.findall(r"(?<!\w)[A-Za-z]{5,}(?!\w)", site["name"]):
            needle = word.casefold()
            if not any(
                needle in text for site_id, text in haystacks.items() if site_id != site["site_id"]
            ):
                return site, word
    pytest.fail("no site name has a word that appears in no other site summary")


def _multi_project_site(atlas: Atlas) -> dict:
    return min(
        atlas.sites,
        key=lambda site: (-site["project_count"], site["name"].casefold(), site["site_id"]),
    )


def _polygon_site(atlas: Atlas) -> dict | None:
    return next(
        (site for site in _by_name(atlas.sites) if site["geometry_type"] in POLYGON_TYPES), None
    )


def _escaping_site(atlas: Atlas) -> dict | None:
    return next(
        (site for site in _by_name(atlas.sites) if any(c in site["name"] for c in "&<>\"'\u2019")),
        None,
    )


def _sample_sites(atlas: Atlas) -> list[dict]:
    picks = [
        _multi_project_site(atlas),
        _polygon_site(atlas),
        _escaping_site(atlas),
        _by_name(atlas.sites)[0],
    ]
    unique: dict[str, dict] = {}
    for site in picks:
        if site is not None:
            unique.setdefault(site["site_id"], site)
    return list(unique.values())


def _country_probe(atlas: Atlas) -> dict:
    total = len(atlas.sites)
    candidates = [country for country in atlas.countries if 2 <= country["site_count"] < total]
    if not candidates:
        _skip_or_fail("needs a country with at least two sites but not every site")
    return min(candidates, key=lambda country: (-country["site_count"], country["country_iso_a2"]))


# --------------------------------------------------------------------------------------------
# Page helpers


def _eventually(page, read, accept, what: str, *, timeout_ms: int = DEFAULT_TIMEOUT_MS):
    """Poll ``read()`` until ``accept(value)``; Python-side polling keeps working under the CSP."""
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        value = read()
        if accept(value):
            return value
        if time.monotonic() >= deadline:
            pytest.fail(
                f"timed out after {timeout_ms} ms waiting for {what}; last value: {value!r:.1500}"
            )
        page.wait_for_timeout(100)


def _goto_ok(page, url: str) -> None:
    response = page.goto(url)
    assert response is not None, f"no response for {url}"
    assert response.status == 200, f"GET {url} -> HTTP {response.status}"


def _wait_until_ready(page) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_MS / 1000
    while page.locator('body[data-atlas-ready="true"]').count() == 0:
        error = page.locator("#atlas-error")
        if error.count() and error.first.is_visible():
            pytest.fail(f"the explorer reported a load error: {error.first.inner_text().strip()!r}")
        if time.monotonic() >= deadline:
            pytest.fail(f"the explorer did not set data-atlas-ready within {READY_TIMEOUT_MS} ms")
        page.wait_for_timeout(100)


def _open_explorer(page, atlas: Atlas, suffix: str = "") -> None:
    _goto_ok(page, atlas.url(suffix))
    _wait_until_ready(page)


def _visible_row_ids(page) -> list[str]:
    ids = page.evaluate(VISIBLE_ROW_IDS_JS)
    assert ids is not None, "#atlas-list is missing"
    return ids


def _count_text_shows(text: str, number: int) -> bool:
    digits = re.sub(r"(?<=\d)[,\u00a0\u202f\u2009](?=\d{3}(?!\d))", "", text)
    return re.search(rf"(?<!\d){number}(?!\d)", digits) is not None


def _expect_result_count(page, number: int) -> None:
    _eventually(
        page,
        lambda: page.locator("#atlas-count").inner_text(),
        lambda text: _count_text_shows(text, number),
        f"#atlas-count to show {number}",
    )


def _expect_rows(page, expected: set[str], what: str) -> list[str]:
    return _eventually(
        page,
        lambda: _visible_row_ids(page),
        lambda ids: len(ids) == len(expected) and set(ids) == expected,
        what,
    )


def _row_button(page, site_id: str):
    row = page.locator(f'#atlas-list [data-site-id="{_css_string(site_id)}"]').first
    expect(row).to_be_attached()
    if row.evaluate("(el) => el.tagName") == "BUTTON":
        return row
    return row.locator("button").first


def _css_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


def _evidence_urls(page, doc: dict) -> set[str]:
    """The site's linkable evidence URLs, serialised the way the browser serialises links."""
    raw = sorted(
        {item["source_url"] for item in doc["evidence"] if _is_http_url(item.get("source_url"))}
    )
    assert raw, f"{doc['site']['site_id']} has no linkable evidence"
    return set(page.evaluate(NORMALIZE_URLS_JS, raw))


def _expect_drawer_shows(page, site: dict, doc: dict) -> None:
    expect(page.locator("#atlas-detail:not([hidden])")).to_have_count(1)
    expect(page.locator("#atlas-detail")).to_be_visible()
    expect(page.locator("#atlas-detail-title")).to_contain_text(site["name"])
    expected = _evidence_urls(page, doc)
    links = page.locator("#atlas-detail a.evidence-link")
    hrefs = _eventually(
        page,
        lambda: set(links.evaluate_all(LINK_URLS_JS)),
        lambda found: expected <= found,
        "every evidence source to be linked in the detail drawer",
    )
    assert all(_is_http_url(href) for href in hrefs), sorted(hrefs)
    for project in doc["projects"]:
        expect(page.locator("#atlas-detail")).to_contain_text(project["name"])


def _show_list(page) -> None:
    """On narrow layouts the list lives behind the List tab."""
    tab = page.locator("#atlas-tab-list")
    if tab.count() and tab.is_visible():
        tab.click()
        expect(page.locator("#atlas-list")).to_be_visible()


def _open_drawer(page, atlas: Atlas, site: dict) -> dict:
    doc = atlas.site_doc(site["site_id"])
    _show_list(page)
    _row_button(page, site["site_id"]).click()
    _expect_drawer_shows(page, site, doc)
    return doc


def _expect_site_hash(page, site_id: str) -> None:
    _eventually(
        page,
        lambda: urlsplit(page.url).fragment,
        lambda fragment: fragment == f"site={site_id}",
        f"#site={site_id} in the URL",
    )


def _reveal_filters(page) -> None:
    """Make the filter controls visible: the list panel on narrow layouts, then the collapsible
    filter group (#atlas-more), which may start closed so that results show above the fold."""
    if page.locator("#atlas-country").is_visible():
        return
    _show_list(page)
    more = page.locator("#atlas-more")
    if not page.locator("#atlas-country").is_visible() and more.count():
        toggle = more.locator("summary").first
        if not toggle.count():
            toggle = page.locator('[aria-controls="atlas-more"]').first
        toggle.click()
    expect(page.locator("#atlas-country")).to_be_visible()


def _select_country(page, country: dict) -> str:
    _reveal_filters(page)
    options = page.locator("#atlas-country option").evaluate_all(
        "(els) => els.map((o) => [o.value, o.textContent || ''])"
    )
    wanted = {
        country["country_iso_a2"].casefold(),
        country.get("slug", "").casefold(),
        country["country"].casefold(),
    }
    value = next((value for value, _ in options if value and value.casefold() in wanted), None)
    if value is None:
        name = _fold(country["country"])
        value = next(
            (value for value, label in options if value and _fold(label).strip().startswith(name)),
            None,
        )
    assert value is not None, f"no #atlas-country option for {country['country']}: {options}"
    page.locator("#atlas-country").select_option(value=value)
    return value


def _resolved_hrefs(page) -> list[str]:
    return [urljoin(page.url, href) for href in page.locator("a[href]").evaluate_all(HREFS_JS)]


def _json_ld_objects(page) -> list[dict]:
    found: list[dict] = []
    for text in page.locator('script[type="application/ld+json"]').evaluate_all(
        "(els) => els.map((el) => el.textContent)"
    ):
        stack = [json.loads(text)]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                found.append(item)
                stack.extend(item.get("@graph", []))
    return found


def _has_type(item: dict, wanted: str) -> bool:
    kind = item.get("@type")
    return kind == wanted or (isinstance(kind, list) and wanted in kind)


def _data_rows(table, page):
    return table.locator("tr").filter(has=page.locator("td"))


def _expect_evidence_table(page, doc: dict) -> None:
    evidence = doc["evidence"]
    expected = _evidence_urls(page, doc)
    tables = page.locator("table.data-table")
    table = None
    for position in range(tables.count()):
        candidate = tables.nth(position)
        if expected <= set(candidate.locator("a[href]").evaluate_all(LINK_URLS_JS)):
            table = candidate
            break
    assert table is not None, "no table.data-table links every evidence source of the site"
    expect(_data_rows(table, page)).to_have_count(len(evidence))
    text = " ".join(table.inner_text().split())
    missing = [item["title"] for item in evidence if " ".join(item["title"].split()) not in text]
    assert not missing, f"evidence titles missing from the table: {missing}"


# --------------------------------------------------------------------------------------------
# API and downloads (served files; no browser needed)


def test_api_documents_parse_and_agree_with_the_index(atlas):
    index = atlas.index
    counts = atlas.counts
    endpoints = index["endpoints"]
    assert index["api_version"] == "1"
    assert {
        "index", "sites", "sites_geojson", "site", "projects", "project", "evidence",
        "evidence_item", "countries", "country", "stats", "versions", "vocabularies",
    } <= set(endpoints)
    assert atlas.get_json(endpoints["index"]) == index

    site_ids = [site["site_id"] for site in atlas.sites]
    assert len(site_ids) == len(set(site_ids)) == counts["physical_sites"]
    collection = atlas.get_json(endpoints["sites_geojson"])
    assert collection["type"] == "FeatureCollection"
    features = collection["features"]
    assert len(features) == len(site_ids)
    assert {feature["id"] for feature in features} == set(site_ids)
    for feature in features:
        assert feature["properties"]["site_id"] == feature["id"]
        assert feature["geometry"]["type"] in ("Point", *POLYGON_TYPES)

    assert len(atlas.get_json(endpoints["projects"])) == counts["projects"]
    assert len(atlas.get_json(endpoints["evidence"])) == counts["evidence"]
    assert len(atlas.countries) == counts["countries"]
    assert sum(country["site_count"] for country in atlas.countries) == counts["physical_sites"]

    stats = atlas.get_json(endpoints["stats"])
    for key in ("physical_sites", "projects", "countries", "evidence"):
        assert stats["counts"][key] == counts[key], key
    versions = atlas.get_json(endpoints["versions"])
    version_ids = [version["id"] for version in versions["versions"]]
    assert versions["current"] == atlas.dataset_id
    assert atlas.dataset_id in version_ids
    assert len(version_ids) == len(set(version_ids))
    vocabularies = atlas.get_json(endpoints["vocabularies"])
    used = {code for site in atlas.sites for code in site["statuses"]}
    assert used <= set(vocabularies["statuses"]), used - set(vocabularies["statuses"])

    first = _by_name(atlas.sites)[0]
    doc = atlas.site_doc(first["site_id"])
    assert doc["api_version"] == "1"
    assert doc["site"]["site_id"] == first["site_id"]
    project_ids = {project["project_id"] for project in first["projects"]}
    assert {project["project_id"] for project in doc["projects"]} == project_ids
    project_id = doc["projects"][0]["project_id"]
    project_doc = atlas.get_json(endpoints["project"].replace("{project_id}", project_id))
    assert project_id in json.dumps(project_doc)
    evidence_id = doc["evidence"][0]["evidence_id"]
    evidence_doc = atlas.get_json(endpoints["evidence_item"].replace("{evidence_id}", evidence_id))
    assert evidence_id in json.dumps(evidence_doc)
    country = atlas.countries[0]
    country_doc = atlas.get_json(endpoints["country"].replace("{iso2}", country["country_iso_a2"]))
    assert country_doc["country"]["country_iso_a2"] == country["country_iso_a2"]
    assert {site["site_id"] for site in country_doc["sites"]} == set(country["site_ids"])
    for site in _sample_sites(atlas):
        assert atlas.get_json(site["api_url"])["site"]["site_id"] == site["site_id"]
        assert atlas.localize(site["url"]) == atlas.url(f"sites/{site['site_id']}/")


def test_downloads_match_their_published_checksums(atlas):
    downloads = atlas.index["downloads"]
    assert downloads, "api/v1/index.json lists no downloads"
    for item in downloads:
        body = atlas.get_bytes(item["url"])
        assert len(body) == item["bytes"], item["url"]
        assert hashlib.sha256(body).hexdigest() == item["sha256"], item["url"]
    for directory in ("latest", atlas.dataset_id):
        sums = atlas.get_bytes(f"downloads/{quote(directory)}/SHA256SUMS").decode("utf-8")
        entries = [line.split("  ", 1) for line in sums.splitlines() if line.strip()]
        names = [name for _, name in entries]
        assert names and names == sorted(names) and "SHA256SUMS" not in names, directory
        zip_name = "datacenter-atlas-latest.zip" if directory == "latest" else (
            f"datacenter-atlas-{atlas.dataset_id}.zip"
        )
        assert zip_name in names, (directory, names)
        for digest, name in entries:
            body = atlas.get_bytes(f"downloads/{quote(directory)}/{quote(name, safe='')}")
            assert hashlib.sha256(body).hexdigest() == digest, f"{directory}/{name}"


def test_not_found_page_uses_absolute_links(atlas):
    document = atlas.get_bytes("404.html").decode("utf-8")
    targets = re.findall(r'\b(?:href|src)="([^"]*)"', document)
    assert targets, "404.html has no links"
    allowed = ("https://", "http://", "#", "mailto:", "data:")
    relative = [target for target in targets if not target.startswith(allowed)]
    # GitHub Pages serves 404.html for any missing path, so relative links would break there.
    assert not relative, f"404.html must only use absolute links: {relative}"
    assert any(t.startswith(atlas.production_base_url) for t in targets)


def test_server_follows_github_pages_rules(atlas):
    # The tests only prove that URLs work in production if the server refuses what Pages refuses.
    assert json.loads(_http_get(atlas.url("api/v1/"))) == atlas.index, "api/v1/ must serve index.json"
    assert _http_status(atlas.url("api/v1/sites/")) == 404, "a directory without an index must be 404"
    missing = atlas.url("this-page-does-not-exist/")
    assert _http_status(missing) == 404
    request = urllib.request.Request(missing, headers={"User-Agent": "datacenter-atlas-e2e"})
    with pytest.raises(urllib.error.HTTPError) as raised:
        _NO_PROXY_OPENER.open(request, timeout=60)
    assert atlas.production_base_url in raised.value.read().decode("utf-8"), "404 must be the site's 404.html"


def _absolute_site_urls(atlas: Atlas, text: str) -> set[str]:
    """Absolute production URLs quoted in ``text`` (URL templates skipped), mapped onto the server."""
    found = set()
    for url in re.findall(re.escape(atlas.production_base_url) + r"[^\s\"'<>()`\\\]]*", text):
        if "{" in url or "}" in url:
            continue
        url = urldefrag(url.rstrip(".,;:!?"))[0].split("?", 1)[0]
        found.add(atlas.localize(url))
    return found


def test_llms_txt_is_a_working_entry_point(atlas):
    headers, body = _http_fetch(atlas.url("llms.txt"))
    assert headers.get("content-type", "").startswith("text/plain"), headers.get("content-type")
    text = body.decode("utf-8")
    first = next(line for line in text.splitlines() if line.strip())
    assert first.startswith("# "), f"llms.txt must start with an H1 title, not {first!r}"
    assert atlas.dataset_id in text, "llms.txt must name the current dataset version"
    for needed in ("api/v1/", "downloads/"):
        assert atlas.production_base_url + needed in text, f"llms.txt has no {needed} URL"
    folded = text.casefold()
    assert any(
        name in folded for name in ("cc by 4.0", "cc-by-4.0", "creative commons attribution 4.0")
    ), "llms.txt must state the licence"
    for caveat in ("last reported", "footprint", "unknown", "coverage"):
        assert caveat in folded, f"llms.txt must carry the {caveat!r} caveat"
    urls = _absolute_site_urls(atlas, text)
    broken = sorted(url for url in urls if _http_status(url) != 200)
    assert not broken, f"llms.txt links to URLs that are not 200: {broken}"


def _json_pointer(document, pointer: str):
    node = document
    for part in [item for item in pointer.split("/") if item]:
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _openapi_sample_values(atlas: Atlas) -> dict[str, str]:
    site = _by_name(atlas.sites)[0]
    doc = atlas.site_doc(site["site_id"])
    return {
        "site": site["site_id"],
        "project": doc["projects"][0]["project_id"],
        "evidence": doc["evidence"][0]["evidence_id"],
        "iso": atlas.countries[0]["country_iso_a2"],
        "country": atlas.countries[0]["country_iso_a2"],
    }


def _template_key(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{}", path)


def test_openapi_describes_every_static_endpoint(atlas):
    endpoints = atlas.index["endpoints"]
    assert "openapi" in endpoints, "api/v1/index.json must link the OpenAPI description"
    openapi_url = atlas.localize(endpoints["openapi"])
    spec = atlas.get_json(openapi_url)
    assert str(spec.get("openapi", "")).startswith("3.1"), spec.get("openapi")
    assert spec.get("info", {}).get("title") and spec.get("info", {}).get("version")
    paths = spec.get("paths") or {}
    assert paths, "the OpenAPI description has no paths"
    servers = spec.get("servers") or [{}]
    server = str(servers[0].get("url", "")).rstrip("/") + "/"
    assert server.startswith(atlas.production_base_url), f"server {server!r} is not the production site"
    described = {_template_key(path.lstrip("/")) for path in paths}
    missing = [
        name for name, url in endpoints.items()
        if url.startswith(server) and _template_key(url[len(server):]) not in described
    ]
    assert not missing, f"index.json endpoints missing from the OpenAPI paths: {missing}"

    documents = {openapi_url: spec}

    def resolve(node, base: str):
        seen = 0
        while isinstance(node, dict) and "$ref" in node:
            seen += 1
            assert seen < 20, f"$ref loop at {node['$ref']}"
            target, _, pointer = node["$ref"].partition("#")
            if target:
                base = atlas.localize(urljoin(base, target))
                if base not in documents:
                    documents[base] = atlas.get_json(base)
            node = _json_pointer(documents[base], pointer)
        return node, base

    def all_refs(node, base: str) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("$ref"), str):
                resolve(node, base)
            for value in node.values():
                all_refs(value, base)
        elif isinstance(node, list):
            for value in node:
                all_refs(value, base)

    all_refs(spec, openapi_url)  # every schema the description points to must be served
    samples = _openapi_sample_values(atlas)
    for path, item in sorted(paths.items()):
        operation = item.get("get")
        assert operation, f"{path} has no GET operation"

        def fill(match: re.Match) -> str:
            name = match.group(1).casefold()
            key = next((key for key in samples if key in name), None)
            assert key is not None, f"{path}: no sample value for the {{{match.group(1)}}} parameter"
            return quote(samples[key], safe="")

        url = atlas.localize(urljoin(server, re.sub(r"\{([^}]*)\}", fill, path.lstrip("/"))))
        raw = atlas.get_bytes(url)
        response, base = resolve((operation.get("responses") or {}).get("200") or {}, openapi_url)
        content = response.get("content") or {}
        assert content, f"{path}: the 200 response has no content"
        media_type, media = next(iter(content.items()))
        if "json" not in media_type:
            raw.decode("utf-8")  # e.g. text/csv: served and UTF-8
            continue
        body = json.loads(raw.decode("utf-8"))
        schema, _ = resolve(media.get("schema") or {}, base)
        kind = schema.get("type")
        if kind == "array":
            assert isinstance(body, list), f"{path}: the schema says array"
        elif kind == "object":
            assert isinstance(body, dict), f"{path}: the schema says object"
            missing_keys = [key for key in schema.get("required", []) if key not in body]
            assert not missing_keys, f"{path}: required keys missing from the response: {missing_keys}"


def test_download_directories_have_landing_pages(atlas):
    # Citations and the API point at downloads/<id>/ directories; on GitHub Pages they only
    # resolve through an index.html, which must link every file the directory holds.
    headers, body = _http_fetch(atlas.url("downloads/"))
    assert headers.get("content-type", "").startswith("text/html")
    listing = {urljoin(atlas.url("downloads/"), href) for href in re.findall(r'href="([^"]+)"', body.decode("utf-8"))}
    for directory in ("latest", atlas.dataset_id):
        assert atlas.url(f"downloads/{quote(directory)}/") in listing, f"downloads/ does not link {directory}/"
    for directory in ("latest", atlas.dataset_id):
        base = atlas.url(f"downloads/{quote(directory)}/")
        headers, body = _http_fetch(base)
        assert headers.get("content-type", "").startswith("text/html"), (directory, headers)
        page = body.decode("utf-8")
        sums = atlas.get_bytes(f"downloads/{quote(directory)}/SHA256SUMS").decode("utf-8")
        names = [line.split("  ", 1)[1] for line in sums.splitlines() if line.strip()]
        hrefs = {urljoin(base, href) for href in re.findall(r'href="([^"]+)"', page)}
        unlinked = [name for name in names if urljoin(base, quote(name, safe="")) not in hrefs]
        assert not unlinked, f"downloads/{directory}/ does not link {unlinked}"


def test_public_metadata_matches_the_build(atlas):
    """README.md, CITATION.cff and DATA_LICENSE.md state the facts of the build being tested."""
    endpoints = atlas.index["endpoints"]
    facts = check_public_metadata.facts_from_documents(
        index=atlas.index,
        stats=atlas.get_json(endpoints["stats"]),
        versions=atlas.get_json(endpoints["versions"]),
        countries=atlas.countries,
        projects=atlas.get_json(endpoints["projects"]),
        evidence=atlas.get_json(endpoints["evidence"]),
        config=check_public_metadata.load_config(REPO_ROOT),
        citation=atlas.get_json(endpoints["citation"]) if "citation" in endpoints else None,
    )
    problems = check_public_metadata.check(REPO_ROOT, facts)
    assert not problems, "\n".join(problems)


def test_live_checks_pass_against_this_build(atlas):
    live_checks = _load_sibling("live_checks")

    def fetch(url: str):
        return live_checks.http_get(atlas.localize(url))

    report = live_checks.check_deployment(
        atlas.production_base_url, atlas.index, token="e2e", fetch=fetch
    )
    assert report.checked > 20
    assert not report.problems, "\n".join(report.problems)


# --------------------------------------------------------------------------------------------
# Explorer


def test_explorer_lists_and_maps_every_site(open_page, atlas):
    expected = set(atlas.sites_by_id)
    page, guard = open_page()
    _open_explorer(page, atlas)
    _expect_rows(page, expected, "one list row per site")
    _expect_result_count(page, len(expected))
    markers = page.locator("#atlas-map path.atlas-marker")
    expect(markers).to_have_count(len(expected))
    _eventually(
        page, lambda: markers.evaluate_all(DRAWN_PATHS_JS), lambda drawn: drawn > 0,
        "markers to be drawn on the map",
    )
    if any(site["geometry_type"] in POLYGON_TYPES for site in atlas.sites):
        assert page.locator("#atlas-map path.atlas-polygon").count() >= 1, "no .atlas-polygon paths"
    assert page.locator("#atlas-detail[hidden]").count() == 1, "the detail drawer starts closed"
    expect(page.locator("#atlas-error")).to_be_hidden()
    summary = page.evaluate(EXPLORER_SUMMARY_TEXT_JS)
    for key in ("physical_sites", "projects", "countries"):
        assert _count_text_shows(summary, atlas.counts[key]), f"summary strip lacks {key}"
    guard.assert_clean()


def test_explorer_controls_match_the_contract(open_page, atlas):
    page, guard = open_page()
    _open_explorer(page, atlas)

    def option_values(selector: str) -> list[str]:
        return page.locator(f"{selector} option").evaluate_all("(els) => els.map((o) => o.value)")

    assert set(option_values("#atlas-locator")) == {"any", "official_boundary", "polygon", "point"}
    assert set(option_values("#atlas-sort")) == {"name", "country", "newest", "oldest", "projects"}
    for selector in ("#atlas-from", "#atlas-to"):
        values = option_values(selector)
        assert values and all(v == "" or re.fullmatch(r"\d{4}-\d{2}", v) for v in values), values
    checkboxes = page.locator('#atlas-status input[type="checkbox"][name="status"]')
    offered = set(checkboxes.evaluate_all("(els) => els.map((el) => el.value)"))
    used = {code for site in atlas.sites for code in site["statuses"]}
    assert used <= offered, used - offered
    countries = [value for value in option_values("#atlas-country") if value]
    assert len(countries) >= atlas.counts["countries"]
    assert page.locator("#atlas-power").get_attribute("type") == "checkbox"
    for selector in (
        "#atlas-search", "#atlas-clear", "#atlas-fit", "#atlas-export-csv",
        "#atlas-export-geojson", "#atlas-copy-link", "#atlas-detail-close", "#atlas-detail-title",
        "#atlas-tab-list", "#atlas-tab-map",
    ):
        expect(page.locator(selector)).to_have_count(1)
    count = page.locator("#atlas-count")
    assert count.get_attribute("aria-live") == "polite" or count.get_attribute("role") == "status"
    guard.assert_clean()


def test_search_filters_rows_and_round_trips_through_the_url(open_page, atlas):
    site, word = _search_probe(atlas)
    page, guard = open_page()
    _open_explorer(page, atlas)
    page.locator("#atlas-search").fill(word)
    _expect_rows(page, {site["site_id"]}, f"searching {word!r} to leave only {site['name']!r}")
    _expect_result_count(page, 1)
    _eventually(
        page, lambda: _query(page.url).get("q", [""])[0], lambda q: q.casefold() == word.casefold(),
        "the search to be written to ?q=",
    )
    shared, shared_guard = open_page()
    _goto_ok(shared, page.url)
    _wait_until_ready(shared)
    expect(shared.locator("#atlas-search")).to_have_value(
        re.compile(re.escape(word), re.IGNORECASE)
    )
    _expect_rows(shared, {site["site_id"]}, "the shared ?q= URL to reproduce the result")
    page.locator("#atlas-search").fill("")
    _expect_rows(page, set(atlas.sites_by_id), "clearing the search to show every site")
    guard.assert_clean()
    shared_guard.assert_clean()


def test_country_filter_round_trips_through_the_url(open_page, atlas):
    country = _country_probe(atlas)
    expected = set(country["site_ids"])
    page, guard = open_page()
    _open_explorer(page, atlas)
    value = _select_country(page, country)
    _expect_rows(page, expected, f"the {country['country']} filter")
    _expect_result_count(page, len(expected))
    query = _eventually(
        page, lambda: _query(page.url), lambda q: "country" in q, "the country to reach the URL"
    )
    assert query["country"][0].casefold() == value.casefold()

    shared, shared_guard = open_page()  # a new context: only the URL carries the view
    _goto_ok(shared, page.url)
    _wait_until_ready(shared)
    expect(shared.locator("#atlas-country")).to_have_value(value)
    _expect_rows(shared, expected, "the shared ?country= URL to reproduce the filter")

    page.locator("#atlas-clear").click()
    _expect_rows(page, set(atlas.sites_by_id), "Clear filters to show every site")
    _eventually(
        page, lambda: _query(page.url), lambda q: "country" not in q, "Clear to reset the URL"
    )
    guard.assert_clean()
    shared_guard.assert_clean()


URL_STATE_CASES = (
    "status",
    "locator-polygon",
    "locator-point",
    "locator-official-boundary",
    "power",
    "sort-newest",
    "sort-projects",
)


def _url_state_case(atlas: Atlas, case: str):
    """(query, expected site ids, order check or None, control assertion) for one URL state."""
    sites = atlas.sites
    every = {site["site_id"] for site in sites}

    def matching(predicate) -> set[str]:
        chosen = {site["site_id"] for site in sites if predicate(site)}
        if not chosen:
            _skip_or_fail(f"no site matches the {case} case in this dataset")
        return chosen

    if case == "status":
        tally: dict[str, int] = {}
        for site in sites:
            for code in set(site["statuses"]):
                tally[code] = tally.get(code, 0) + 1
        candidates = sorted((n, code) for code, n in tally.items() if 2 <= n < len(sites))
        if not candidates:
            _skip_or_fail("no status is shared by some but not all sites")
        code = candidates[0][1]
        return (
            f"?status={quote(code)}",
            matching(lambda site: code in site["statuses"]),
            None,
            lambda page: expect(
                page.locator(f'#atlas-status input[name="status"][value="{_css_string(code)}"]')
            ).to_be_checked(),
        )
    if case.startswith("locator-"):
        value = {"locator-polygon": "polygon", "locator-point": "point"}.get(
            case, "official_boundary"
        )
        predicate = {
            "polygon": lambda site: site["geometry_type"] in POLYGON_TYPES,
            "point": lambda site: site["geometry_type"] == "Point",
            "official_boundary": lambda site: site["official_boundary"] is True,
        }[value]
        return (
            f"?locator={value}",
            matching(predicate),
            None,
            lambda page: expect(page.locator("#atlas-locator")).to_have_value(value),
        )
    if case == "power":
        return (
            "?power=1",
            matching(lambda site: bool(site["power_observations"])),
            None,
            lambda page: expect(page.locator("#atlas-power")).to_be_checked(),
        )
    sort, field = {
        "sort-newest": ("newest", "newest_status_as_of"),
        "sort-projects": ("projects", "project_count"),
    }[case]
    return (
        f"?sort={sort}",
        every,
        field,
        lambda page: expect(page.locator("#atlas-sort")).to_have_value(sort),
    )


@pytest.mark.parametrize("case", URL_STATE_CASES)
def test_url_query_reproduces_the_view(open_page, atlas, case):
    query, expected, order_field, control = _url_state_case(atlas, case)
    page, guard = open_page()
    _open_explorer(page, atlas, query)
    ids = _expect_rows(page, expected, f"{query} to filter the list")
    _expect_result_count(page, len(expected))
    control(page)
    if order_field is not None:
        values = [atlas.sites_by_id[site_id][order_field] for site_id in ids]
        known = [value for value in values if value is not None]
        assert known == sorted(known, reverse=True), f"{query}: {order_field} not descending"
    guard.assert_clean()


def test_selecting_a_row_opens_the_drawer_and_escape_returns_focus(open_page, atlas):
    site = _multi_project_site(atlas)
    page, guard = open_page()
    _open_explorer(page, atlas)
    _open_drawer(page, atlas, site)
    labelled_by = page.locator("#atlas-detail").get_attribute("aria-labelledby") or ""
    assert "atlas-detail-title" in labelled_by.split(), labelled_by
    _expect_site_hash(page, site["site_id"])
    page.keyboard.press("Escape")
    expect(page.locator("#atlas-detail[hidden]")).to_have_count(1)
    _eventually(
        page, lambda: page.evaluate(FOCUSED_ROW_JS), lambda focused: focused == site["site_id"],
        "Escape to return focus to the originating list row",
    )
    guard.assert_clean()


def test_browser_back_closes_the_drawer(open_page, atlas):
    site = _multi_project_site(atlas)
    page, guard = open_page()
    _open_explorer(page, atlas)
    _open_drawer(page, atlas, site)
    _expect_site_hash(page, site["site_id"])
    page.go_back()
    expect(page.locator("#atlas-detail[hidden]")).to_have_count(1)
    assert "site=" not in urlsplit(page.url).fragment
    guard.assert_clean()


def test_site_hash_opens_the_drawer_directly(open_page, atlas):
    site = _polygon_site(atlas) or _multi_project_site(atlas)
    page, guard = open_page()
    _open_explorer(page, atlas, f"#site={site['site_id']}")
    _expect_drawer_shows(page, site, atlas.site_doc(site["site_id"]))
    if site["geometry_type"] in POLYGON_TYPES:
        polygons = page.locator("#atlas-map path.atlas-polygon")
        _eventually(
            page, lambda: polygons.evaluate_all(DRAWN_PATHS_JS), lambda drawn: drawn > 0,
            "the selected site's polygon to be drawn",
        )
    page.locator("#atlas-detail-close").click()
    expect(page.locator("#atlas-detail[hidden]")).to_have_count(1)
    guard.assert_clean()


def test_list_rows_support_arrow_keys_and_enter(open_page, atlas):
    page, guard = open_page()
    _open_explorer(page, atlas)
    ids = _visible_row_ids(page)
    assert len(ids) >= 2
    _row_button(page, ids[0]).focus()
    _eventually(
        page, lambda: page.evaluate(FOCUSED_ROW_JS), lambda f: f == ids[0], "focus on row 1"
    )
    page.keyboard.press("ArrowDown")
    _eventually(
        page, lambda: page.evaluate(FOCUSED_ROW_JS), lambda f: f == ids[1],
        "ArrowDown to move focus to the next row",
    )
    page.keyboard.press("Enter")
    expect(page.locator("#atlas-detail:not([hidden])")).to_have_count(1)
    expect(page.locator("#atlas-detail-title")).to_contain_text(atlas.sites_by_id[ids[1]]["name"])
    guard.assert_clean()


def _expected_export_columns(atlas: Atlas, country: dict) -> list[str] | None:
    """The published per-country CSV's header plus dataset_id, when the API publishes one."""
    template = atlas.index["endpoints"].get("country_csv")
    if not template:
        return None
    text = atlas.get_bytes(template.replace("{iso2}", country["country_iso_a2"])).decode("utf-8-sig")
    return next(csv.reader(io.StringIO(text, newline=""))) + ["dataset_id"]


def test_exports_and_copy_link_follow_the_filtered_view(open_page, atlas, tmp_path):
    country = _country_probe(atlas)
    expected = set(country["site_ids"])
    page, guard = open_page(permissions=("clipboard-read", "clipboard-write"))
    _open_explorer(page, atlas)
    _select_country(page, country)
    _expect_rows(page, expected, f"the {country['country']} filter")

    with page.expect_download() as download:
        page.locator("#atlas-export-csv").click()
    assert atlas.dataset_id in download.value.suggested_filename, download.value.suggested_filename
    csv_path = tmp_path / "filtered.csv"
    download.value.save_as(csv_path)
    rows = list(csv.reader(io.StringIO(csv_path.read_text(encoding="utf-8-sig"), newline="")))
    header = rows[0]
    missing = [column for column in EXPORT_CSV_REQUIRED_COLUMNS if column not in header]
    assert not missing and header[0] == "site_id", f"CSV export header {header} lacks {missing}"
    expected_header = _expected_export_columns(atlas, country)
    if expected_header is not None:
        assert header == expected_header, "the explorer CSV must match the published country CSV + dataset_id"
    assert sorted(row[0] for row in rows[1:]) == sorted(expected)
    version = header.index("dataset_id")
    assert {row[version] for row in rows[1:]} == {atlas.dataset_id}

    with page.expect_download() as download:
        page.locator("#atlas-export-geojson").click()
    geojson_path = tmp_path / "filtered.geojson"
    download.value.save_as(geojson_path)
    collection = json.loads(geojson_path.read_text(encoding="utf-8"))
    assert collection["type"] == "FeatureCollection"
    # The file must say what it is and under which terms it may be reused.
    assert (collection.get("dataset") or {}).get("id") == atlas.dataset_id, collection.get("dataset")
    assert collection.get("license") and collection.get("attribution"), "GeoJSON export lacks its terms"
    exported = [
        feature.get("id") or feature.get("properties", {}).get("site_id")
        for feature in collection["features"]
    ]
    assert sorted(exported) == sorted(expected)

    page.locator("#atlas-copy-link").click()
    copied = _eventually(
        page,
        lambda: page.evaluate("() => navigator.clipboard.readText().catch(() => '')"),
        bool,
        "Copy link to put the current view on the clipboard",
    )
    assert _query(copied) == _query(page.url), (copied, page.url)
    guard.assert_clean()


def _settled_markers(page, expected: int, what: str, *, timeout_ms: int = 20_000) -> dict:
    """Marker geometry once the map has stopped moving (four identical samples, no animation)."""
    samples: list = []

    def read():
        samples.append(page.evaluate(MARKER_GEOMETRY_JS))
        return samples[-1]

    def settled(state) -> bool:
        recent = samples[-4:]
        return (
            len(recent) == 4
            and all(item is not None and item == recent[0] for item in recent)
            and not state["animating"]
            and len(state["markers"]) == expected
        )

    return _eventually(page, read, settled, what, timeout_ms=timeout_ms)


def _markers_outside(state: dict, tolerance: int = 2) -> list:
    left, top, right, bottom = state["box"]
    return [
        (x, y) for x, y in state["markers"]
        if not (left - tolerance <= x <= right + tolerance and top - tolerance <= y <= bottom + tolerance)
    ]


def _country_bounds(atlas: Atlas, country: dict) -> tuple[float, float, float, float]:
    sites = [atlas.sites_by_id[site_id] for site_id in country["site_ids"]]
    lats = [site["latitude"] for site in sites]
    lons = [site["longitude"] for site in sites]
    return min(lats), min(lons), max(lats), max(lons)


def _distant_countries(atlas: Atlas) -> tuple[dict, dict]:
    """Two countries with several sites whose site bounding boxes do not overlap."""
    candidates = sorted(
        (country for country in atlas.countries if country["site_count"] >= 2),
        key=lambda country: (-country["site_count"], country["country_iso_a2"]),
    )
    for first in candidates:
        a = _country_bounds(atlas, first)
        for second in candidates:
            if second is first:
                continue
            b = _country_bounds(atlas, second)
            if a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]:
                return first, second
    _skip_or_fail("needs two countries with several sites and disjoint extents")


def test_auto_fit_follows_consecutive_filters(open_page, atlas):
    # Animated map moves (no reduced-motion preference) must not count as the reader moving the
    # map: every filter change keeps fitting the map to the matching sites.
    first, second = _distant_countries(atlas)
    page, guard = open_page(reduced_motion="no-preference")
    _open_explorer(page, atlas)
    for country in (first, second):
        expected = set(country["site_ids"])
        _select_country(page, country)
        _expect_rows(page, expected, f"the {country['country']} filter")
        state = _settled_markers(
            page, len(expected), f"the map to settle on {country['country']}'s {len(expected)} markers"
        )
        outside = _markers_outside(state)
        assert not outside, (
            f"after filtering to {country['country']}, {len(outside)} of {len(expected)} markers lie "
            f"outside the map {state['box']}: {outside[:5]}"
        )
    guard.assert_clean()


def test_desktop_explorer_shows_results_above_the_fold(open_page, atlas):
    page, guard = open_page(VIEWPORTS["desktop"])
    _open_explorer(page, atlas)
    assert _visible_row_ids(page), "no result rows"
    bottom, height = page.evaluate(
        """() => {
          const row = document.querySelector('#atlas-list [data-site-id]');
          return [row.getBoundingClientRect().bottom, window.innerHeight];
        }"""
    )
    assert bottom <= height, (
        f"the first result row ends at {bottom:.0f}px, below the {height}px viewport: the filters "
        "push every result below the fold"
    )
    guard.assert_clean()


def test_fit_to_results_shows_every_marker_on_a_narrow_phone(open_page, atlas):
    page, guard = open_page(NARROW_VIEWPORT)
    _open_explorer(page, atlas)
    tab = page.locator("#atlas-tab-map")
    if tab.is_visible():
        tab.click()
    expect(page.locator("#atlas-map")).to_be_visible()
    page.locator("#atlas-fit").click()
    state = _settled_markers(page, len(atlas.sites), "the map to settle after Fit to results")
    outside = _markers_outside(state)
    assert not outside, (
        f"Fit to results leaves {len(outside)} of {len(atlas.sites)} markers outside the "
        f"{NARROW_VIEWPORT['width']}px map: {outside[:5]}"
    )
    guard.assert_clean()


def test_phone_detail_sheet_keeps_focus_inside(open_page, atlas):
    # On narrow screens the detail sheet covers the explorer, so it must behave as a modal dialog:
    # Tab and Shift+Tab cycle inside it until it is closed.
    site = _multi_project_site(atlas)
    page, guard = open_page(VIEWPORTS["phone"])
    _open_explorer(page, atlas)
    _open_drawer(page, atlas, site)
    for presses, key in ((40, "Tab"), (10, "Shift+Tab")):
        for number in range(1, presses + 1):
            page.keyboard.press(key)
            inside, label = page.evaluate(FOCUS_IN_DETAIL_JS)
            assert inside, f"{key} press {number} moved focus outside the open sheet, to {label}"
    page.keyboard.press("Escape")
    expect(page.locator("#atlas-detail[hidden]")).to_have_count(1)
    guard.assert_clean()


@pytest.mark.parametrize("variant", sorted(WEBMCP_STUBS))
def test_explorer_works_whatever_webmcp_support(open_page, atlas, variant):
    # WebMCP is optional: without it, or when registration throws or rejects, the explorer must
    # load normally and report no error.
    page, guard = open_page(init_script=WEBMCP_INSTALL_JS % WEBMCP_STUBS[variant])
    _open_explorer(page, atlas)
    _expect_rows(page, set(atlas.sites_by_id), f"every site with WebMCP {variant}")
    guard.assert_clean()


def test_webmcp_tools_drive_the_explorer(open_page, atlas):
    page, guard = open_page(init_script=WEBMCP_RECORDER_JS)
    _open_explorer(page, atlas)
    tools = _eventually(
        page,
        lambda: page.evaluate(WEBMCP_TOOLS_JS),
        lambda found: set(WEBMCP_TOOL_NAMES) <= {tool["name"] for tool in found},
        f"the explorer to register {WEBMCP_TOOL_NAMES} through document.modelContext",
    )
    for tool in tools:
        if tool["name"] not in WEBMCP_TOOL_NAMES:
            continue
        assert tool["executable"] and tool["description"], tool
        assert tool["schemaType"] == "object", tool
        assert tool["annotations"].get("readOnlyHint") is True, tool
        assert tool["annotations"].get("untrustedContentHint") is True, tool

    country = _country_probe(atlas)
    expected = set(country["site_ids"])
    outcome = page.evaluate(
        WEBMCP_EXECUTE_JS,
        ["search_datacenter_sites", {"country": country["country_iso_a2"], "limit": 200}],
    )
    assert "result" in outcome, outcome
    missing = [site_id for site_id in expected if site_id not in outcome["result"]]
    assert not missing, f"search_datacenter_sites did not return {missing[:5]}"
    _expect_rows(page, expected, "search_datacenter_sites to drive the visible list")
    _eventually(
        page, lambda: _query(page.url).get("country", [""])[0].upper(),
        lambda value: value == country["country_iso_a2"].upper(), "the tool's filter to reach the URL",
    )

    site = _by_name([atlas.sites_by_id[site_id] for site_id in expected])[0]  # one of the listed sites
    outcome = page.evaluate(WEBMCP_EXECUTE_JS, ["get_datacenter_site", {"site_id": site["site_id"]}])
    assert site["site_id"] in outcome.get("result", ""), outcome
    _expect_drawer_shows(page, site, atlas.site_doc(site["site_id"]))
    page.evaluate(WEBMCP_EXECUTE_JS, ["get_datacenter_site", {"site_id": "vcc-site-00000000000000000000"}])

    info = page.evaluate(WEBMCP_EXECUTE_JS, ["get_datacenter_dataset_info", {}])
    assert atlas.dataset_id in info.get("result", ""), info
    assert '"caveats"' in info["result"] and '"license"' in info["result"], info

    ended = page.evaluate(
        """(names) => {
          window.dispatchEvent(new PageTransitionEvent('pagehide', { persisted: false }));
          const { calls, unregistered } = window.__atlasWebmcp;
          return names.every((name) => unregistered.includes(name) || calls.some(
            ({ tool, signal }) => tool && tool.name === name && signal && signal.aborted));
        }""",
        list(WEBMCP_TOOL_NAMES),
    )
    assert ended, "pagehide must abort (or unregister) the registered tools"
    guard.assert_clean()


# --------------------------------------------------------------------------------------------
# Static pages


def test_static_pages_work_without_javascript(open_page, atlas):
    page, guard = open_page(javascript=False)
    _goto_ok(page, atlas.url("sites/"))
    table = page.locator("#sites-table")
    expect(_data_rows(table, page)).to_have_count(len(atlas.sites))
    linked = {
        match.group(1)
        for href in _resolved_hrefs(page)
        if (match := re.search(r"/sites/([^/?#]+)/$", urldefrag(href)[0]))
    }
    assert set(atlas.sites_by_id) <= linked

    _goto_ok(page, atlas.url("countries/"))
    expect(_data_rows(page.locator("main table.data-table").first, page)).to_have_count(
        len(atlas.countries)
    )
    country = _country_probe(atlas)
    _goto_ok(page, atlas.localize(country["url"]))
    expect(page.locator("h1").first).to_contain_text(country["country"])
    expect(_data_rows(page.locator("main table.data-table").first, page)).to_have_count(
        country["site_count"]
    )

    issues = atlas.index["repository_url"].rstrip("/") + "/issues/new"
    for site in _sample_sites(atlas):
        site_id = site["site_id"]
        _goto_ok(page, atlas.localize(site["url"]))
        assert page.title().startswith(site["name"]), page.title()
        expect(page.locator("h1").first).to_contain_text(site["name"])
        _expect_evidence_table(page, atlas.site_doc(site_id))
        hrefs = _resolved_hrefs(page)
        assert atlas.url(f"api/v1/sites/{site_id}.json") in hrefs, "no JSON link"
        wanted = {
            "template": ["correction.yml"],
            "title": [f"Correction: {site['name']}"],
            "site_id": [site_id],
        }
        corrections = [_query(href) for href in hrefs if href.startswith(issues + "?")]
        assert any(
            all(query.get(key) == value for key, value in wanted.items()) for query in corrections
        ), f"no correction link with {wanted}: {corrections}"
        site_map = page.locator(".site-map")
        expect(site_map).to_have_count(1)
        assert site_map.inner_text().strip(), "the map has no text fallback without JavaScript"
        places = [item for item in _json_ld_objects(page) if _has_type(item, "Place")]
        assert places and places[0].get("name") == site["name"], places
    guard.assert_clean()


def test_sites_table_filters_and_sorts_with_javascript(open_page, atlas):
    site, word = _search_probe(atlas)
    page, guard = open_page()
    _goto_ok(page, atlas.url("sites/"))
    table = page.locator("#sites-table")
    page.locator('input.filter-input[data-filter-table="sites-table"]').fill(word)
    rows = _eventually(
        page, lambda: table.evaluate(VISIBLE_TABLE_ROWS_JS), lambda found: len(found) == 1,
        f"filtering the table by {word!r} to leave one row",
    )
    assert site["name"] in " ".join(rows[0])
    _eventually(
        page, lambda: page.locator('[data-filter-count="sites-table"]').inner_text(),
        lambda text: _count_text_shows(text, 1), "the filter count to show 1",
    )
    page.locator('input.filter-input[data-filter-table="sites-table"]').fill("")
    _eventually(
        page, lambda: len(table.evaluate(VISIBLE_TABLE_ROWS_JS)), lambda n: n == len(atlas.sites),
        "clearing the filter to show every row",
    )

    header = table.locator("th").filter(has_text=re.compile(r"\bProjects\b")).first
    column = header.evaluate("(th) => th.cellIndex")
    toggle = header.locator("button")
    (toggle.first if toggle.count() else header).click()
    direction = _eventually(
        page, lambda: header.get_attribute("aria-sort"), lambda v: v in ("ascending", "descending"),
        "the Projects header to report aria-sort",
    )
    rows = table.evaluate(VISIBLE_TABLE_ROWS_JS)
    values = [int(re.sub(r"\D", "", row[column]) or 0) for row in rows]
    assert values == sorted(values, reverse=direction == "descending"), values
    guard.assert_clean()


def test_site_page_map_renders_with_javascript(open_page, atlas):
    site = _polygon_site(atlas) or _by_name(atlas.sites)[0]
    page, guard = open_page()
    _goto_ok(page, atlas.localize(site["url"]))
    expect(
        page.locator(".site-map.leaflet-container, .site-map .leaflet-container").first
    ).to_be_attached()
    shapes = page.locator(".site-map path, .site-map .leaflet-marker-icon, .site-map canvas")
    _eventually(
        page, lambda: shapes.count(), lambda n: n >= 1, "the site geometry or marker to render"
    )
    guard.assert_clean()


def test_table_first_columns_stay_readable_at_820px(open_page, atlas):
    # The first column names the row (site, source title, metric); it must never be squeezed
    # to a sliver by wide neighbours.
    sites = [_multi_project_site(atlas)]
    powered = next((site for site in _by_name(atlas.sites) if site["power_observations"]), None)
    if powered is not None and powered["site_id"] != sites[0]["site_id"]:
        sites.append(powered)
    page, guard = open_page(VIEWPORTS["tablet"])
    failures = []
    for path in ("sites/", *(atlas.localize(site["url"])[len(atlas.base_url):] for site in sites)):
        _goto_ok(page, atlas.url(path))
        widths = page.evaluate(FIRST_COLUMN_WIDTHS_JS)
        assert widths, f"{path} has no table.data-table rows"
        narrow = [item for item in widths if item[0] < 96]
        if narrow:
            failures.append(f"{path}: first-column cells narrower than 96px: {narrow[:3]}")
    assert not failures, "\n".join(failures)
    guard.assert_clean()


def test_data_and_api_page_links_resolve(open_page, atlas):
    page, guard = open_page()
    failures = []
    for path in ("data/", "api/"):
        _goto_ok(page, atlas.url(path))
        page_url = urldefrag(page.url)[0]
        anchors = set(page.locator("[id]").evaluate_all("(els) => els.map((el) => el.id)"))
        targets: set[str] = set()
        for href in _resolved_hrefs(page):
            target, fragment = urldefrag(href)
            if target == page_url:
                if fragment and fragment not in anchors:
                    failures.append(f"{path}: #{fragment} has no matching id")
                continue
            if target.startswith(atlas.production_base_url):
                target = atlas.localize(target)
            if target.startswith(atlas.base_url):
                # The server follows GitHub Pages: a directory URL is 200 only through its
                # index.html or index.json, never through a generated listing.
                targets.add(target)
        assert targets, f"{path} links to nothing on the site"
        # Absolute URLs quoted in snippets, prose and JSON-LD must exist as well, directory URLs
        # included: a reader who pastes one must not get a 404.
        text = page.evaluate(SNIPPET_TEXT_JS)
        for found in re.findall(re.escape(atlas.production_base_url) + r"[^\s\"'<>()`\\]*", text):
            if "{" in found or "}" in found:
                continue  # URL template such as .../sites/{site_id}.json
            found = urldefrag(found.rstrip(".,;:!?]"))[0].split("?", 1)[0]
            targets.add(atlas.localize(found))
        for url in sorted(targets):
            response = page.request.head(url)
            if response.status != 200:
                failures.append(f"{path}: {url} -> HTTP {response.status}")
            response.dispose()
    assert not failures, "\n".join(failures)
    guard.assert_clean()


def test_no_horizontal_overflow_at_360px(open_page, atlas):
    site = _multi_project_site(atlas)
    country = _country_probe(atlas)
    page, guard = open_page(NARROW_VIEWPORT)
    failures = []

    def check(label: str) -> None:
        result = page.evaluate(OVERFLOW_JS)
        if result["width"] > result["viewport"] + 1:
            failures.append(
                f"{label}: {result['width']}px wide at a {result['viewport']}px viewport; "
                f"overflowing: {result['offenders']}"
            )

    _open_explorer(page, atlas)
    check("explorer")
    _open_drawer(page, atlas, site)
    check("explorer with the detail sheet open")
    for path in (
        *STATIC_PAGES,
        f"sites/{site['site_id']}/",
        atlas.localize(country["url"])[len(atlas.base_url):],
    ):
        _goto_ok(page, atlas.url(path))
        check(path)
    assert not failures, "\n".join(failures)
    guard.assert_clean()


# --------------------------------------------------------------------------------------------
# Screenshots and accessibility


@pytest.mark.parametrize("name", list(VIEWPORTS))
def test_screenshots(open_page, atlas, screenshot_dir, name):
    viewport = VIEWPORTS[name]
    size = f"{viewport['width']}x{viewport['height']}"
    wide = viewport["width"] >= WIDE_LAYOUT_MIN_WIDTH
    site = _multi_project_site(atlas)
    page, guard = open_page(viewport)

    _open_explorer(page, atlas)
    for tab in ("#atlas-tab-list", "#atlas-tab-map"):
        assert page.locator(tab).is_visible() == (not wide), f"{tab} visibility at {size}"
    page.screenshot(path=screenshot_dir / f"explorer-{size}.png", animations="disabled")
    if not wide:
        page.locator("#atlas-tab-map").click()
        expect(page.locator("#atlas-map")).to_be_visible()
        markers = page.locator("#atlas-map path.atlas-marker")
        _eventually(
            page, lambda: markers.evaluate_all(DRAWN_PATHS_JS), lambda drawn: drawn > 0,
            "markers to be drawn after switching to the map tab",
        )
        page.screenshot(path=screenshot_dir / f"explorer-map-{size}.png", animations="disabled")
        page.locator("#atlas-tab-list").click()
        expect(page.locator("#atlas-list")).to_be_visible()
    _open_drawer(page, atlas, site)
    page.screenshot(path=screenshot_dir / f"explorer-drawer-{size}.png", animations="disabled")

    _goto_ok(page, atlas.localize(site["url"]))
    page.screenshot(
        path=screenshot_dir / f"site-page-{size}.png", full_page=True, animations="disabled"
    )
    _goto_ok(page, atlas.url("data/"))
    page.screenshot(
        path=screenshot_dir / f"data-page-{size}.png", full_page=True, animations="disabled"
    )
    # Long table pages: the viewport around the first table (a full-page capture of 200 rows
    # would exceed the browser's maximum screenshot height on phones).
    for name, path in (("sites-index", "sites/"), ("dictionary", "data/dictionary/"), ("api-page", "api/")):
        _goto_ok(page, atlas.url(path))
        table = page.locator("main table.data-table").first
        if table.count():
            table.scroll_into_view_if_needed()
        page.screenshot(path=screenshot_dir / f"{name}-{size}.png", animations="disabled")
    guard.assert_clean()

    if wide:
        dark, dark_guard = open_page(viewport, color_scheme="dark")
        _open_explorer(dark, atlas)
        dark.screenshot(path=screenshot_dir / f"explorer-dark-{size}.png", animations="disabled")
        _goto_ok(dark, atlas.localize(site["url"]))
        dark.screenshot(
            path=screenshot_dir / f"site-page-dark-{size}.png",
            full_page=True,
            animations="disabled",
        )
        dark_guard.assert_clean()


# (viewport, colour scheme, what to audit). The phone run audits the open detail sheet, which
# covers the explorer there; the others audit the explorer, its drawer and every static page.
AXE_RUNS = {
    "desktop-light": ("desktop", "light", "pages"),
    "desktop-dark": ("desktop", "dark", "pages"),
    "phone-sheet": ("phone", "light", "sheet"),
}
# Serious findings that fail the run (all critical ones do too); other serious ones are reported.
AXE_BLOCKING_SERIOUS = frozenset({"color-contrast", "aria-dialog-name", "scrollable-region-focusable"})


@pytest.mark.parametrize("run", list(AXE_RUNS))
def test_no_blocking_accessibility_violations(open_page, atlas, run):
    if os.environ.get("ATLAS_E2E_REQUIRED") == "1":
        from axe_playwright_python.sync_playwright import Axe
    else:
        Axe = pytest.importorskip("axe_playwright_python.sync_playwright").Axe
    axe = Axe()
    viewport, scheme, scope = AXE_RUNS[run]
    site = _multi_project_site(atlas)
    # axe is injected by evaluation, which the Content-Security-Policy would block.
    page, guard = open_page(VIEWPORTS[viewport], bypass_csp=True, color_scheme=scheme)
    blocking: list[str] = []
    serious: list[str] = []

    def audit(label: str) -> None:
        for violation in axe.run(page, context=AXE_CONTEXT).response["violations"]:
            nodes = violation.get("nodes", [])[:5]
            targets = [", ".join(map(str, node.get("target", []))) for node in nodes]
            impact = violation.get("impact")
            line = f"{run} {label}: {violation['id']} ({impact}): {violation.get('help')} {targets}"
            if impact == "critical" or (impact == "serious" and violation["id"] in AXE_BLOCKING_SERIOUS):
                blocking.append(line)
            elif impact == "serious":
                serious.append(line)

    _open_explorer(page, atlas)
    if scope == "pages":
        audit("explorer")
    _open_drawer(page, atlas, site)
    audit("explorer with the detail drawer open")
    if scope == "pages":
        for path in (*STATIC_PAGES, atlas.localize(site["url"])[len(atlas.base_url):]):
            _goto_ok(page, atlas.url(path))
            audit(path)
    if serious:
        report = "\n".join(serious)
        warnings.warn(f"serious accessibility findings (reported, not failing):\n{report}")
    assert not blocking, "\n".join(blocking)
    guard.assert_clean()
