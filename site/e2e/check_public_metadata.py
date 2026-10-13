"""Check (or rewrite) the dataset facts written outside the site build.

README.md, CITATION.cff and DATA_LICENSE.md state dataset dates, counts and citation metadata. They are not produced by ``scripts/build_public_site.py``, so
they need to be refreshed when the data changes. This script reads
the built site's API (``api/v1/*.json``) and the repository's ``site/config.json`` and:

- regenerates ``CITATION.cff`` and the marked blocks in README.md and DATA_LICENSE.md
  (``<!-- atlas:NAME -->`` ... ``<!-- /atlas:NAME -->``) from those facts;
- checks figures in the hand-written prose (for example "98 of the 197 sites") against the build;
- flags commands and links that still name an earlier v0.18 checkpoint.

Usage (standard library only)::

    python3 scripts/build_public_site.py --output _site --force
    python3 site/e2e/check_public_metadata.py --site _site          # check; exit 1 when stale
    python3 site/e2e/check_public_metadata.py --site _site --write  # rewrite the generated parts

CI runs the check after every build (``.github/workflows/pages.yml`` and ``clean-clone.yml``).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
import textwrap
from typing import Any, Callable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
CITATION_PATH = "CITATION.cff"
README_PATH = "README.md"
DATA_LICENSE_PATH = "DATA_LICENSE.md"
CONTRIBUTING_PATH = "CONTRIBUTING.md"
DEFAULT_TITLE = "Data Center Atlas: Verified Construction Core"
KEYWORDS = (
    "data centers",
    "data centres",
    "construction",
    "digital infrastructure",
    "geospatial",
    "open data",
    "provenance",
    "GeoJSON",
)
DRAFT_MARK = "-v0.18-draft-"
DRAFT_ID = re.compile(r"\b\d{4}-\d{2}-\d{2}-v0\.18-draft-[a-z0-9]+(?:-[a-z0-9]+)*\b")
NUMBER_WORDS = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen", "twenty",
)


class MetadataError(RuntimeError):
    """The built site or the repository cannot be read."""


@dataclass(frozen=True)
class Facts:
    """What the build says about the current dataset."""

    index: Mapping[str, Any]
    stats: Mapping[str, Any]
    versions: Mapping[str, Any]
    countries: Sequence[Mapping[str, Any]]
    projects: Sequence[Mapping[str, Any]]
    evidence: Sequence[Mapping[str, Any]]
    config: Mapping[str, Any]
    # api/v1/citation.json when the build publishes one: the README then quotes the same citation.
    citation: Mapping[str, Any] | None = None

    @property
    def dataset(self) -> Mapping[str, Any]:
        return self.index["dataset"]

    @property
    def counts(self) -> Mapping[str, Any]:
        return self.dataset["counts"]

    @property
    def base_url(self) -> str:
        return str(self.index.get("base_url") or self.config["base_url"])

    @property
    def batch(self) -> str | None:
        """The draft builder's --batch name of the current dataset (None for a preview)."""
        identifier = str(self.dataset["id"])
        return identifier.split(DRAFT_MARK, 1)[1] if DRAFT_MARK in identifier else None


# --------------------------------------------------------------------------------------------
# Reading the build


def _endpoint_path(index: Mapping[str, Any], key: str, default: str) -> str:
    url = str(index.get("endpoints", {}).get(key) or "")
    base = str(index.get("base_url") or "")
    if base and url.startswith(base):
        return url[len(base):]
    return default


def load_facts(site_dir: Path, repo: Path) -> Facts:
    """Read the API documents of a built site directory and the repository config."""

    def read(path: str) -> Any:
        target = site_dir / path
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise MetadataError(f"cannot read {target}: {error}") from None

    index = read("api/v1/index.json")
    return facts_from_documents(
        index=index,
        stats=read(_endpoint_path(index, "stats", "api/v1/stats.json")),
        versions=read(_endpoint_path(index, "versions", "api/v1/versions.json")),
        countries=read(_endpoint_path(index, "countries", "api/v1/countries.json")),
        projects=read(_endpoint_path(index, "projects", "api/v1/projects.json")),
        evidence=read(_endpoint_path(index, "evidence", "api/v1/evidence.json")),
        config=load_config(repo),
        citation=read(_endpoint_path(index, "citation", "")) if index.get("endpoints", {}).get("citation") else None,
    )


def load_config(repo: Path) -> Mapping[str, Any]:
    path = repo / "site" / "config.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MetadataError(f"cannot read {path}: {error}") from None


def facts_from_documents(**documents: Any) -> Facts:
    facts = Facts(**documents)
    for key in ("id", "label", "checkpoint_date", "lifecycle_reference_date", "counts"):
        if key not in facts.dataset:
            raise MetadataError(f"api/v1/index.json dataset has no {key!r}")
    return facts


# --------------------------------------------------------------------------------------------
# Small formatting helpers


def number_word(value: int) -> str:
    return NUMBER_WORDS[value] if 0 <= value < len(NUMBER_WORDS) else str(value)


_UNBREAKABLE = re.compile(r"\[[^\]]*\]\([^)]*\)|\*\*[^*]+\*\*|`[^`]+`")


def wrap(text: str, *, width: int = 100, first: str = "", rest: str = "") -> str:
    """textwrap.fill that never breaks inside a Markdown link, bold span or code span."""
    protected = _UNBREAKABLE.sub(lambda match: match.group(0).replace(" ", "\x00"), text)
    filled = textwrap.fill(
        protected, width=width, initial_indent=first, subsequent_indent=rest,
        break_long_words=False, break_on_hyphens=False,
    )
    return filled.replace("\x00", " ")


def author_parts(config: Mapping[str, Any]) -> tuple[str, str]:
    """(family, given) names from config author.name ("Kian Kyars" -> ("Kyars", "Kian"))."""
    name = str(config.get("author", {}).get("name", "")).strip()
    if not name:
        raise MetadataError("site/config.json has no author.name")
    words = name.split()
    return words[-1], " ".join(words[:-1])


def dataset_title(facts: Facts) -> str:
    title = facts.dataset.get("title") or facts.index.get("dataset_title") or facts.config.get("dataset_title")
    return str(title) if title else DEFAULT_TITLE


def _country(facts: Facts, name_or_code: str) -> Mapping[str, Any] | None:
    wanted = name_or_code.strip().casefold()
    for country in facts.countries:
        if wanted in (str(country.get("country", "")).casefold(), str(country.get("country_iso_a2", "")).casefold()):
            return country
    return None


def locator_exceptions(facts: Facts) -> list[str]:
    """Names of the projects whose geometry is host-estate context only, not a reviewed locator."""
    return sorted({
        str(project.get("name") or project.get("project_id"))
        for project in facts.projects
        if "host_estate_context" in str(project.get("geometry_use_scope") or "")
        or "host_estate_context" in str(project.get("verification_posture") or "")
    })


def _exception_sentence(facts: Facts, *, markdown: bool) -> str:
    names = locator_exceptions(facts)
    if not names:
        return ""
    listed = ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1]
    url = f"{facts.base_url}methodology/#locators"
    subject = f"{number_word(len(names)).capitalize()} project{'s' if len(names) != 1 else ''}"
    verb = "has" if len(names) == 1 else "have"
    where = f"; see the [methodology]({url})." if markdown else f" ({url})."
    return f"{subject} ({listed}) {verb} host-estate context only, not a reviewed locator{where}"


def osm_geometry_counts(facts: Facts) -> tuple[int, int]:
    """(projects, sites) whose geometry evidence row is licensed ODbL-1.0 (OpenStreetMap)."""
    licences = {item.get("evidence_id"): item.get("license") for item in facts.evidence}
    projects = [
        project for project in facts.projects
        if licences.get(project.get("geometry_evidence_id")) == "ODbL-1.0"
    ]
    return len(projects), len({project.get("site_id") for project in projects})


# --------------------------------------------------------------------------------------------
# Generated text


def citation_cff(facts: Facts) -> str:
    dataset, counts, config = facts.dataset, facts.counts, facts.config
    base = facts.base_url
    family, given = author_parts(config)
    abstract = (
        "An open dataset of data-centre construction worldwide. Each project has a dated, "
        "authoritative observation of physical construction work, a "
        "sourced location with its precision recorded"
        f"{' (or, for a listed locator exception, host-estate context only)' if locator_exceptions(facts) else ''}"
        ", and source records with URLs, licences, retrieval times and content hashes. "
        f"Data updated {dataset['checkpoint_date']}: "
        f"{counts['physical_sites']} physical sites with {counts['projects']} projects in "
        f"{counts['countries']} countries, backed by {counts['evidence']} evidence rows. "
        f"{_exception_sentence(facts, markdown=False) + ' ' if locator_exceptions(facts) else ''}"
        "Statuses are the last observed physical status, not the current status; locators are not building "
        "footprints; capacity is unknown unless a typed observation exists; and the dataset is not a census. "
        "Atlas-authored data are licensed CC BY 4.0; geometries derived from OpenStreetMap are © "
        "OpenStreetMap contributors under the ODbL 1.0, and other third-party facts keep their source terms "
        "(see DATA_LICENSE.md)."
    )
    message = (
        "If you use this dataset, please cite it as below. Archived data files remain unchanged at "
        f"{base}downloads/<dataset_id>/<file> and are "
        f"listed at {base}versions/."
    )
    repository = str(config["repository_url"]).rstrip("/")
    lines = [
        "# Generated by site/e2e/check_public_metadata.py --write from the built site; do not edit by hand.",
        "cff-version: 1.2.0",
        "message: >-",
        wrap(message, width=80, first="  ", rest="  "),
        "type: dataset",
        f'title: "{dataset_title(facts)}"',
        "abstract: >-",
        wrap(abstract, width=80, first="  ", rest="  "),
        "authors:",
        f"  - family-names: {family}",
        f"    given-names: {given}",
    ]
    if config.get("author", {}).get("url"):
        lines.append(f'    website: "{config["author"]["url"]}"')
    lines += [
        f'repository-code: "{repository}"',
        f'url: "{base}"',
    ]
    doi = facts.dataset.get("doi") or config.get("doi")
    if doi:
        lines += [f'doi: "{doi}"', "identifiers:", "  - type: doi", f'    value: "{doi}"',
                  "    description: Concept DOI (all versions)"]
    lines += [
        f"license: {config.get('data_license', {}).get('id', 'CC-BY-4.0')}",
        f'license-url: "{repository}/blob/main/DATA_LICENSE.md"',
        f'version: "{dataset["id"]}"',
        f'date-released: "{dataset["checkpoint_date"]}"',
        "keywords:",
        *[f"  - {keyword}" for keyword in KEYWORDS],
    ]
    return "\n".join(lines) + "\n"


def readme_current_dataset(facts: Facts) -> str:
    dataset, counts = facts.dataset, facts.counts
    bullets = [
        f"**Coverage:** **{counts['physical_sites']} physical sites**, **{counts['projects']} construction "
        f"projects** and **{counts['countries']} countries**.",
        f"**Data updated:** {dataset['checkpoint_date']}.",
        f"**Construction observations:** {dataset.get('window_start', '?')} to "
        f"{dataset.get('observation_window_end', dataset['lifecycle_reference_date'])}. "
        "Each record includes its source and observation date.",
    ]
    return "\n".join(wrap(text, first="- ", rest="  ") for text in bullets)


def citation_parts(facts: Facts) -> tuple[str, str]:
    """(APA-style reference, BibTeX entry) for the current version: the build's own citation.json
    when it publishes one, so the README and the site cite identically."""
    published = facts.citation or {}
    if isinstance(published.get("apa"), str) and isinstance(published.get("bibtex"), str):
        title = dataset_title(facts)
        return published["apa"].replace(title, f"*{title}*", 1), published["bibtex"].strip()
    family, given = author_parts(facts.config)
    year = str(facts.dataset["checkpoint_date"])[:4]
    title = dataset_title(facts)
    reference = (
        f"{family}, {given[:1]}. ({year}). *{title}* [Data set; updated {facts.dataset['checkpoint_date']}]. {facts.base_url}"
    )
    key = re.sub(r"[^a-z0-9]", "", f"{family}{year}datacenteratlas".lower())
    bibtex = "\n".join([
        f"@misc{{{key},",
        f'  author = "{family}, {given}",',
        f'  title  = "{title}",',
        f'  year   = "{year}",',
        f'  note   = "Data updated {facts.dataset["checkpoint_date"]}; archive ID {facts.dataset["id"]}",',
        f'  url    = "{facts.base_url}"',
        "}",
    ])
    return reference, bibtex


def readme_citation(facts: Facts) -> str:
    reference, bibtex = citation_parts(facts)
    quoted = wrap(reference, first="> ", rest="> ")
    return f"{quoted}\n\n```bibtex\n{bibtex}\n```"


def readme_version_files(facts: Facts) -> str:
    base, identifier = facts.base_url, facts.dataset["id"]
    text = (
        "`downloads/latest/` contains the current data. For reproducible work, use the "
        f"[archived files]({base}downloads/{identifier}/) and verify them against their "
        f"[`SHA256SUMS`]({base}downloads/{identifier}/SHA256SUMS)."
    )
    return wrap(text)


def license_example(facts: Facts) -> str:
    text = (
        f"Data: {facts.config.get('site_name', 'Data Center Atlas')} ({facts.config['author']['name']}), "
        f"{facts.base_url}, data updated {facts.dataset['checkpoint_date']}, CC BY 4.0. Includes data © OpenStreetMap "
        "contributors (ODbL 1.0) and from the other sources listed in the dataset's ATTRIBUTION.txt."
    )
    return wrap(text, first="> ", rest="> ")


def license_osm_count(facts: Facts) -> str:
    projects, sites = osm_geometry_counts(facts)
    return (
        f"{projects} of the {facts.counts['projects']} project geometries, on {sites} sites, in the "
        f"{facts.dataset['checkpoint_date']} data snapshot"
    )


# Generated blocks: (file, block name, generator, inline). Inline blocks sit inside a sentence.
BLOCKS: tuple[tuple[str, str, Callable[[Facts], str], bool], ...] = (
    (README_PATH, "current-dataset", readme_current_dataset, False),
    (README_PATH, "version-files", readme_version_files, False),
    (README_PATH, "citation", readme_citation, False),
    (DATA_LICENSE_PATH, "attribution-example", license_example, False),
    (DATA_LICENSE_PATH, "osm-geometry-count", license_osm_count, True),
)


def _block_pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"(<!-- atlas:{re.escape(name)} -->)(.*?)(<!-- /atlas:{re.escape(name)} -->)", re.DOTALL
    )


def replace_block(text: str, name: str, content: str, *, inline: bool = False) -> str:
    pattern = _block_pattern(name)
    matches = pattern.findall(text)
    if len(matches) != 1:
        raise MetadataError(f"expected exactly one <!-- atlas:{name} --> block, found {len(matches)}")
    body = content if inline else f"\n{content}\n"
    return pattern.sub(lambda match: match.group(1) + body + match.group(3), text)


def block_content(text: str, name: str) -> str | None:
    found = _block_pattern(name).findall(text)
    return found[0][1] if len(found) == 1 else None


def _strip_blocks(text: str) -> str:
    return re.sub(r"<!-- atlas:([a-z0-9-]+) -->.*?<!-- /atlas:\1 -->", "", text, flags=re.DOTALL)


# --------------------------------------------------------------------------------------------
# Checks on hand-written prose


Check = Callable[[re.Match[str]], "str | None"]
COUNTRY_NAME = r"[A-Z][\w.'-]*(?: [A-Z][\w.'-]*)*"
COUNTRY_LIST = re.compile(
    rf"\b(?:the )?((?:the )?{COUNTRY_NAME}(?:, (?:the )?{COUNTRY_NAME})*,? and (?:the )?{COUNTRY_NAME}) "
    r"hold (\d+) of the\b"
)


def _equals(expected: Any, what: str, group: int = 1) -> Check:
    def check(match: re.Match[str]) -> str | None:
        found = match.group(group)
        if str(expected).casefold() == found.casefold() or (
            isinstance(expected, int) and found.casefold() == number_word(expected)
        ):
            return None
        return f"says {found} {what}; the build has {expected}"

    return check


def _prose_checks(facts: Facts) -> list[tuple[str, re.Pattern[str], Check]]:
    """(name, pattern, check) for figures and references in hand-written prose."""
    counts = facts.counts
    batch = facts.batch
    current_id = str(facts.dataset["id"])
    projects = facts.projects

    def total(field: str) -> int:
        return sum(len(project.get(field) or []) for project in projects)

    def known(field: str) -> int:
        return sum(1 for project in projects if project.get(field) not in (None, "", [], "unknown"))

    gates = facts.stats.get("release_gates") or {}
    imagery = gates.get("imagery_outcomes_complete", {}).get("actual")
    if imagery is None:
        imagery = sum(
            1 for project in projects
            if not str(project.get("imagery_review_outcome") or "not_reviewed").startswith("not_reviewed")
        )

    def countries_hold(match: re.Match[str]) -> str | None:
        found = 0
        for name in re.split(r",\s*|\s+and\s+", match.group(1)):
            name = re.sub(r"^the\s+", "", name.strip(), flags=re.IGNORECASE)
            country = _country(facts, name)
            if country is None:
                return f"names {name!r}, which is not a country in the build"
            found += int(country["site_count"])
        return None if match.group(2) == str(found) else f"the build has {found} sites in those countries"

    def other_draft(match: re.Match[str]) -> str | None:
        return None if match.group(0) == current_id else f"is not the current version {current_id}"

    def stale_batch(match: re.Match[str]) -> str | None:
        if batch is None or match.group(1) == batch:
            return None
        return f"the current checkpoint's batch is {batch}"

    def stale_test_module(match: re.Match[str]) -> str | None:
        expected = None if batch is None else "test_expansion_200_" + batch.replace("-", "_")
        if expected is None or match.group(1) == expected:
            return None
        return f"the current checkpoint's test module is {expected}"

    return [
        ("site total", re.compile(r"\bof the (\d+) (?:physical )?sites\b"), _equals(counts["physical_sites"], "sites")),
        ("project total", re.compile(r"\bof the (\d+) (?:construction )?projects\b"), _equals(counts["projects"], "projects")),
        ("geometry total", re.compile(r"\bof the (\d+) project geometries\b"), _equals(counts["projects"], "geometries")),
        ("point sites", re.compile(r"\b(\d+) sites are located by a point\b"), _equals(counts.get("point_sites"), "point sites")),
        ("polygon sites", re.compile(r"\blocated by a point and (\d+) by a polygon\b"), _equals(counts.get("polygon_sites"), "polygon sites")),
        ("official boundaries", re.compile(r"\b[Oo]nly (\d+) projects use an official site boundary\b"), _equals(counts.get("official_boundary_projects"), "projects")),
        ("power projects", re.compile(r"\b(\d+) of the \d+ projects carry one\b"), _equals(counts.get("power_observation_projects"), "projects")),
        ("power observations", re.compile(r"\bcarry one \((\d+) observations\b"), _equals(total("power_observations"), "observations")),
        ("positional uncertainty", re.compile(r"\bpositional uncertainty is known for (\d+) projects\b"), _equals(known("horizontal_uncertainty_metres"), "projects")),
        ("role claims", re.compile(r"\bhas (\d+) role claims\b"), _equals(total("role_claims"), "role claims")),
        ("workload observations", re.compile(r"\band (\d+) workload observations\b"), _equals(total("workloads"), "workload observations")),
        ("operating models", re.compile(r"\boperating model is known for (\d+) projects\b"), _equals(known("operating_model"), "projects")),
        ("imagery outcomes", re.compile(r"\b(\w+) projects carry an imagery-review outcome\b"), _equals(imagery, "projects")),
        ("country coverage", COUNTRY_LIST, countries_hold),
        ("dataset version", DRAFT_ID, other_draft),
        ("draft builder batch", re.compile(r"--batch ([a-z0-9-]+)"), stale_batch),
        ("checkpoint test module", re.compile(r"\b(test_expansion_200_[a-z0-9_]+)\b"), stale_test_module),
    ]


def prose_problems(facts: Facts, path: str, text: str) -> list[str]:
    """Stale figures and references in the hand-written parts of one file."""
    problems = []
    prose = re.sub(r"\s+", " ", _strip_blocks(text))
    for name, pattern, rule in _prose_checks(facts):
        for match in pattern.finditer(prose):
            message = rule(match)
            if message:
                problems.append(f"{path}: {name}: {match.group(0)!r}: {message}")
    return problems


# --------------------------------------------------------------------------------------------
# Check and write


def check(repo: Path, facts: Facts) -> list[str]:
    """Every stale or missing fact, as human-readable lines (empty when all agree)."""
    problems: list[str] = []

    def read(path: str) -> str:
        try:
            return (repo / path).read_text(encoding="utf-8")
        except OSError as error:
            raise MetadataError(f"cannot read {repo / path}: {error}") from None

    citation = read(CITATION_PATH)
    if citation != citation_cff(facts):
        problems.append(f"{CITATION_PATH} is not what the build generates; run --write")
    texts = {path: read(path) for path in (README_PATH, DATA_LICENSE_PATH, CONTRIBUTING_PATH)}
    for path, name, generate, inline in BLOCKS:
        found = block_content(texts[path], name)
        expected = generate(facts) if inline else f"\n{generate(facts)}\n"
        if found is None:
            problems.append(f"{path}: needs exactly one <!-- atlas:{name} --> ... <!-- /atlas:{name} --> block")
        elif found != expected:
            problems.append(f"{path}: the {name} block is stale; run --write")
    for path, text in texts.items():
        problems += prose_problems(facts, path, text)
    return problems


def write(repo: Path, facts: Facts) -> list[str]:
    """Rewrite CITATION.cff and the generated blocks; return the files that changed."""
    changed = []
    updates: dict[str, str] = {CITATION_PATH: citation_cff(facts)}
    for path, name, generate, inline in BLOCKS:
        text = updates.get(path) or (repo / path).read_text(encoding="utf-8")
        updates[path] = replace_block(text, name, generate(facts), inline=inline)
    for path, text in updates.items():
        target = repo / path
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8")
            changed.append(path)
    return changed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the dataset facts in README.md, CITATION.cff and DATA_LICENSE.md against a built site.")
    parser.add_argument("--site", required=True, type=Path, help="built site directory (contains api/v1/index.json)")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help="repository root (default: this checkout)")
    parser.add_argument("--write", action="store_true", help="rewrite CITATION.cff and the generated blocks, then check")
    args = parser.parse_args(argv)
    try:
        facts = load_facts(args.site, args.repo)
        if args.write:
            for path in write(args.repo, facts):
                print(f"updated {path}")
        problems = check(args.repo, facts)
    except MetadataError as error:
        print(f"check_public_metadata: {error}", file=sys.stderr)
        return 2
    if problems:
        print(f"The public metadata disagrees with the build of {facts.dataset['id']}:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        if not args.write:
            print("Run: python3 site/e2e/check_public_metadata.py --site <built site> --write, then fix the "
                  "remaining prose by hand.", file=sys.stderr)
        return 1
    print(f"README.md, CITATION.cff, DATA_LICENSE.md and CONTRIBUTING.md agree with {facts.dataset['id']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
