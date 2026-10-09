"""Check the deployed public site, and optionally report dead evidence links.

After a deploy, CI waits until the live ``api/v1/index.json`` reports the pushed commit, then checks
what users and scripts rely on: every API endpoint answers 200 with JSON and
``Access-Control-Allow-Origin: *``, the main pages and machine-readable entry points
(``llms.txt``, the OpenAPI description, the feed, the sitemap) answer 200, and every file listed in
``downloads/latest/SHA256SUMS`` (and in the index's download list) matches its checksum.

The weekly monitor also runs ``--check-links``: one polite GET per distinct evidence ``source_url``
(at most one request per second, 15-second timeout, the first 64 KiB read). Only 404, 410 and
unknown hosts count as dead; 401, 403, 429, 5xx, timeouts and TLS errors are listed as unverified,
because many publishers refuse automated requests. The link report never fails the run.

Usage (standard library only)::

    python3 site/e2e/live_checks.py --base-url https://kiankyars.github.io/datacenter-atlas/ \\
        --wait-for-commit "$GITHUB_SHA" --timeout 600
    python3 site/e2e/live_checks.py --base-url ... --check-links --report link-report.md
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import socket
import sys
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
import urllib.error
from urllib.parse import quote, urljoin, urlsplit
import urllib.request

USER_AGENT = "datacenter-atlas-live-check/1 (+https://github.com/kiankyars/datacenter-atlas)"
PAGES = (
    "", "sites/", "countries/", "data/", "data/dictionary/", "api/", "methodology/", "versions/",
    "about/", "about/attribution/", "sitemap.xml", "feed.xml", "robots.txt", "llms.txt",
)
JSON_TYPES = ("application/json", "application/geo+json")
DEAD_STATUSES = frozenset({404, 410})
LINK_READ_BYTES = 64 * 1024


class LiveCheckError(RuntimeError):
    pass


@dataclass
class Response:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes

    def header(self, name: str) -> str:
        return self.headers.get(name.lower(), "")


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    checked: int = 0

    def fail(self, message: str) -> None:
        self.problems.append(message)


Fetch = Callable[[str], Response]


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get(url: str, *, timeout: float = 30.0, limit: int | None = None) -> Response:
    """GET ``url``; HTTP errors become a Response with their status instead of an exception."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with _opener().open(request, timeout=timeout) as response:
            body = response.read(limit) if limit else response.read()
            headers = {key.lower(): value for key, value in response.headers.items()}
            return Response(response.geturl(), response.status, headers, body)
    except urllib.error.HTTPError as error:
        headers = {key.lower(): value for key, value in (error.headers or {}).items()}
        return Response(url, error.code, headers, b"")


def cache_busted(url: str, token: str) -> str:
    separator = "&" if urlsplit(url).query else "?"
    return f"{url}{separator}live-check={quote(token, safe='')}"


# --------------------------------------------------------------------------------------------
# Deployment checks


def wait_for_commit(base_url: str, commit: str, *, timeout: float, interval: float = 15.0,
                    fetch: Fetch = http_get, sleep: Callable[[float], None] = time.sleep,
                    clock: Callable[[], float] = time.monotonic) -> Mapping[str, Any]:
    """Poll api/v1/index.json until build.source_commit is ``commit``; return that index."""
    deadline = clock() + timeout
    attempt = 0
    last = "no response"
    while True:
        attempt += 1
        url = cache_busted(urljoin(base_url, "api/v1/index.json"), f"{commit}-{attempt}")
        try:
            response = fetch(url)
            if response.status == 200:
                index = json.loads(response.body.decode("utf-8"))
                served = str(index.get("build", {}).get("source_commit") or "")
                if served == commit:
                    return index
                last = f"serves commit {served or 'unknown'}"
            else:
                last = f"HTTP {response.status}"
        except (OSError, ValueError) as error:
            last = f"{type(error).__name__}: {error}"
        if clock() >= deadline:
            raise LiveCheckError(f"{base_url} did not serve commit {commit} within {timeout:.0f} s ({last})")
        sleep(interval)


def _expect_api_file(report: Report, response: Response, what: str) -> Any:
    """An API response: 200, CORS for everyone, and JSON (or CSV) that parses."""
    report.checked += 1
    if response.status != 200:
        report.fail(f"{what}: HTTP {response.status} for {response.url}")
        return None
    if response.header("access-control-allow-origin") != "*":
        report.fail(f"{what}: no Access-Control-Allow-Origin: * on {response.url}")
    media_type = response.header("content-type").split(";", 1)[0].strip().lower()
    path = urlsplit(response.url).path
    if path.endswith(".csv"):
        if media_type != "text/csv":
            report.fail(f"{what}: Content-Type {media_type or 'missing'} for {response.url}")
        try:
            response.body.decode("utf-8")
        except UnicodeDecodeError as error:
            report.fail(f"{what}: not UTF-8 at {response.url} ({error})")
        return None
    if media_type not in JSON_TYPES:
        report.fail(f"{what}: Content-Type {media_type or 'missing'} for {response.url}")
    try:
        return json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        report.fail(f"{what}: invalid JSON at {response.url} ({error})")
        return None


def _template_samples(index: Mapping[str, Any], fetch: Fetch, token: str) -> dict[str, str]:
    """One real identifier for each URL-template placeholder, read from the collection endpoints."""
    endpoints = index.get("endpoints", {})
    samples: dict[str, str] = {}
    sources = (
        ("sites", "site_id", "site_id"),
        ("projects", "project_id", "project_id"),
        ("evidence", "evidence_id", "evidence_id"),
        ("countries", "iso2", "country_iso_a2"),
    )
    for endpoint, placeholder, key in sources:
        url = endpoints.get(endpoint)
        if not url:
            continue
        response = fetch(cache_busted(url, token))
        if response.status != 200:
            continue
        try:
            records = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(records, list) and records and isinstance(records[0], dict) and records[0].get(key):
            samples[placeholder] = str(records[0][key])
    return samples


def check_deployment(base_url: str, index: Mapping[str, Any], *, token: str, fetch: Fetch = http_get) -> Report:
    report = Report()
    endpoints = index.get("endpoints", {})
    samples = _template_samples(index, fetch, token)
    for name in sorted(endpoints):
        url = str(endpoints[name])
        if "{" in url:
            placeholder = url[url.index("{") + 1:url.index("}")]
            if placeholder not in samples:
                report.fail(f"endpoint {name}: no sample value for {{{placeholder}}}")
                continue
            url = url.replace("{" + placeholder + "}", quote(samples[placeholder], safe=""))
        if not url.startswith(base_url):
            report.fail(f"endpoint {name}: {url} is not under {base_url}")
            continue
        _expect_api_file(report, fetch(cache_busted(url, token)), f"endpoint {name}")
    for path in PAGES:
        url = urljoin(base_url, path)
        response = fetch(cache_busted(url, token))
        report.checked += 1
        if response.status != 200:
            report.fail(f"page {path or '/'}: HTTP {response.status}")
    _check_downloads(report, base_url, index, token=token, fetch=fetch)
    return report


def _check_downloads(report: Report, base_url: str, index: Mapping[str, Any], *, token: str, fetch: Fetch) -> None:
    sums_url = urljoin(base_url, "downloads/latest/SHA256SUMS")
    response = fetch(cache_busted(sums_url, token))
    report.checked += 1
    if response.status != 200:
        report.fail(f"downloads/latest/SHA256SUMS: HTTP {response.status}")
        return
    expected: dict[str, str] = {}
    for line in response.body.decode("utf-8").splitlines():
        if line.strip():
            digest, name = line.split("  ", 1)
            expected[urljoin(sums_url, quote(name, safe=""))] = digest
    for item in index.get("downloads", []):
        url = str(item.get("url", ""))
        if url in expected and expected[url] != item.get("sha256"):
            report.fail(f"{url}: index.json says {item.get('sha256')}, SHA256SUMS says {expected[url]}")
        expected.setdefault(url, str(item.get("sha256", "")))
    for url, digest in sorted(expected.items()):
        body = fetch(cache_busted(url, token))
        report.checked += 1
        if body.status != 200:
            report.fail(f"{url}: HTTP {body.status}")
        elif hashlib.sha256(body.body).hexdigest() != digest:
            report.fail(f"{url}: SHA-256 {hashlib.sha256(body.body).hexdigest()} does not match {digest}")


# --------------------------------------------------------------------------------------------
# Evidence links


@dataclass(frozen=True)
class LinkResult:
    url: str
    outcome: str  # "ok", "dead" or "unverified"
    detail: str


def classify_link(url: str, *, timeout: float = 15.0, fetch: Callable[..., Response] = http_get) -> LinkResult:
    try:
        response = fetch(url, timeout=timeout, limit=LINK_READ_BYTES)
    except urllib.error.URLError as error:
        reason = error.reason
        if isinstance(reason, socket.gaierror):
            return LinkResult(url, "dead", f"unknown host ({reason})")
        return LinkResult(url, "unverified", f"{type(reason).__name__}: {reason}")
    except (OSError, ValueError) as error:
        return LinkResult(url, "unverified", f"{type(error).__name__}: {error}")
    if response.status in DEAD_STATUSES:
        return LinkResult(url, "dead", f"HTTP {response.status}")
    if 200 <= response.status < 400:
        return LinkResult(url, "ok", f"HTTP {response.status}")
    return LinkResult(url, "unverified", f"HTTP {response.status}")


def evidence_links(evidence: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    """Evidence records grouped by their http(s) source_url, in URL order."""
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for item in evidence:
        url = item.get("source_url")
        if isinstance(url, str) and urlsplit(url).scheme in ("http", "https"):
            grouped.setdefault(url, []).append(item)
    return dict(sorted(grouped.items()))


def check_links(evidence: Iterable[Mapping[str, Any]], *, delay: float = 1.0, timeout: float = 15.0,
                classify: Callable[[str], LinkResult] | None = None,
                sleep: Callable[[float], None] = time.sleep) -> tuple[list[LinkResult], dict[str, list[Mapping[str, Any]]]]:
    grouped = evidence_links(evidence)
    run = classify or (lambda url: classify_link(url, timeout=timeout))
    results = []
    for position, url in enumerate(grouped):
        if position and delay > 0:
            sleep(delay)
        results.append(run(url))
    return results, grouped


# GitHub issue bodies hold at most 65,536 characters; the report is trimmed to fit.
MAX_REPORT_CHARS = 60_000


def link_report(base_url: str, results: Sequence[LinkResult], grouped: Mapping[str, Sequence[Mapping[str, Any]]],
                *, dataset_id: str, checked_on: str, max_chars: int = MAX_REPORT_CHARS) -> str:
    dead = [result for result in results if result.outcome == "dead"]
    unverified = [result for result in results if result.outcome == "unverified"]
    lines = [
        f"Evidence link check of dataset `{dataset_id}` on {checked_on}: {len(results)} distinct source URLs, "
        f"{len(dead)} dead (HTTP 404 or 410, or unknown host), {len(unverified)} unverified (the server refused "
        "or failed the request; often a bot block, not a dead link).",
        "",
        "A dead link does not change any record: published versions are frozen. Fix it in a later checkpoint "
        "with an archived copy or a replacement source.",
    ]

    def row(result: LinkResult) -> str:
        records = grouped.get(result.url, [])
        evidence_ids = ", ".join(sorted({f"`{item.get('evidence_id')}`" for item in records}))
        sites = sorted({site for item in records for site in item.get("site_ids") or []})
        pages = ", ".join(f"[{site}]({base_url}sites/{site}/)" for site in sites)
        detail = result.detail.replace("|", "/")
        url = result.url.replace("|", "%7C").replace("<", "%3C").replace(">", "%3E").replace(" ", "%20")
        return f"| <{url}> | {detail} | {evidence_ids} | {pages} |"

    def table(title: str, items: Sequence[LinkResult]) -> None:
        if not items:
            return
        lines.extend(["", f"### {title}", "", "| Source URL | Result | Evidence | Site pages |", "| --- | --- | --- | --- |"])
        used = sum(len(line) + 1 for line in lines)
        for position, result in enumerate(items):
            text = row(result)
            if used + len(text) + 200 > max_chars:
                lines.append(f"| and {len(items) - position} more | | | |")
                return
            lines.append(text)
            used += len(text) + 1

    table("Dead", dead)
    table("Unverified", unverified)
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the deployed public site.")
    parser.add_argument("--base-url", required=True, help="the site's base URL, ending in /")
    parser.add_argument("--wait-for-commit", metavar="SHA", help="first wait until the site serves this commit")
    parser.add_argument("--timeout", type=float, default=600.0, help="seconds to wait for the commit (default 600)")
    parser.add_argument("--skip-deployment-checks", action="store_true", help="only run --check-links")
    parser.add_argument("--check-links", action="store_true", help="also check every evidence source URL")
    parser.add_argument("--link-delay", type=float, default=1.0, help="seconds between link requests (default 1)")
    parser.add_argument("--report", help="write the link report (Markdown) to this file")
    parser.add_argument("--summary", help="append a Markdown summary to this file (e.g. $GITHUB_STEP_SUMMARY)")
    args = parser.parse_args(argv)
    base_url = args.base_url if args.base_url.endswith("/") else args.base_url + "/"
    token = args.wait_for_commit or str(int(time.time()))
    summary: list[str] = []
    try:
        if args.wait_for_commit:
            index = wait_for_commit(base_url, args.wait_for_commit, timeout=args.timeout)
            print(f"{base_url} serves commit {args.wait_for_commit}")
        else:
            response = http_get(cache_busted(urljoin(base_url, "api/v1/index.json"), token))
            if response.status != 200:
                raise LiveCheckError(f"api/v1/index.json: HTTP {response.status}")
            index = json.loads(response.body.decode("utf-8"))
    except (LiveCheckError, OSError, ValueError) as error:
        print(f"live_checks: {error}", file=sys.stderr)
        return 1
    status = 0
    if not args.skip_deployment_checks:
        report = check_deployment(base_url, index, token=token)
        summary.append(f"Live site: {report.checked} checks, {len(report.problems)} problems.")
        if report.problems:
            status = 1
            print(f"{len(report.problems)} problems on the live site:", file=sys.stderr)
            for problem in report.problems:
                print(f"- {problem}", file=sys.stderr)
                summary.append(f"- {problem}")
        else:
            print(f"Live site OK: {report.checked} checks passed.")
    if args.check_links:
        evidence_url = index.get("endpoints", {}).get("evidence") or urljoin(base_url, "api/v1/evidence.json")
        response = http_get(cache_busted(evidence_url, token))
        if response.status != 200:
            print(f"live_checks: evidence.json: HTTP {response.status}", file=sys.stderr)
            return 1
        results, grouped = check_links(json.loads(response.body.decode("utf-8")), delay=args.link_delay)
        text = link_report(
            base_url, results, grouped, dataset_id=str(index.get("dataset", {}).get("id", "?")),
            checked_on=time.strftime("%Y-%m-%d", time.gmtime()),
        )
        if args.report:
            with open(args.report, "w", encoding="utf-8") as handle:
                handle.write(text)
        dead = sum(1 for result in results if result.outcome == "dead")
        print(f"Evidence links: {len(results)} checked, {dead} dead.")
        summary.append(text)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(summary) + "\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
