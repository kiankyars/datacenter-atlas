"""Release notes, tag and asset list for a GitHub Release of the current data snapshot.

The ``release`` job of ``.github/workflows/pages.yml`` (enabled by the repository variable
``ATLAS_GITHUB_RELEASES=true``) runs after tests and before deployment, then creates the release
``data-<dataset id>`` once per snapshot with the files listed here attached, so every update
gets a frozen, citable copy of its derived formats (and, with the Zenodo GitHub integration,
a DOI).

Usage (standard library only)::

    python3 site/e2e/release_notes.py --site _site --notes notes.md --assets assets.txt
    # prints the tag, the title and "prerelease" or "release" on three lines
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

TAG_PREFIX = "data-"
# Attached in this order when present in downloads/<id>/ (the zip first: it holds everything).
ASSET_NAMES = (
    "datacenter-atlas-{id}.zip",
    "SHA256SUMS",
    "sites.csv",
    "projects.csv",
    "evidence.csv",
    "sites.geojson",
    "atlas.sqlite",
    "atlas.xlsx",
    "atlas.json",
    "datapackage.json",
)
CAVEATS = (
    "Each status is the **last reported project status** as of a dated source, not the status today.",
    "Locators place a site on the map; they are **not building footprints** or construction extents.",
    "A missing capacity, role or workload is **unknown, not zero**.",
    "Coverage is incomplete and varies by country.",
)
MAX_LISTED_SITES = 60


class ReleaseError(RuntimeError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseError(f"cannot read {path}: {error}") from None


def release_tag(dataset_id: str) -> str:
    return f"{TAG_PREFIX}{dataset_id}"


def release_title(dataset: Mapping[str, Any]) -> str:
    """A unique title naming the dataset: its update date, then the rest of its ID.

    ``2026-10-15-research-thirtieth`` becomes "Data Center Atlas · 2026-10-15 · research-thirtieth";
    an ID that is only the date gives "Data Center Atlas · 2026-10-13". An ID that does not start
    with the update date is shown whole.
    """
    updated = str(dataset.get("updated_at", dataset["checkpoint_date"]))
    identifier = str(dataset["id"])
    if identifier == updated:
        return f"Data Center Atlas · {updated}"
    suffix = identifier.removeprefix(f"{updated}-")
    return f"Data Center Atlas · {updated} · {suffix}"


def asset_paths(site: Path, dataset_id: str) -> list[Path]:
    directory = site / "downloads" / dataset_id
    if not directory.is_dir():
        raise ReleaseError(f"{directory} does not exist")
    paths = [directory / name.format(id=dataset_id) for name in ASSET_NAMES]
    found = [path for path in paths if path.is_file()]
    if not any(path.name.endswith(".zip") for path in found):
        raise ReleaseError(f"{directory} has no datacenter-atlas-{dataset_id}.zip")
    return found


_MARKDOWN_SPECIAL = str.maketrans({char: f"\\{char}" for char in "\\`*_[]<>#|"})


def markdown_text(value: Any) -> str:
    """Third-party text (site and country names) escaped for Markdown."""
    return str(value).translate(_MARKDOWN_SPECIAL)


def _site_line(base_url: str, site: Mapping[str, Any] | None, site_id: str) -> str:
    if site is None:
        return f"- `{site_id}`"
    name = markdown_text(site.get("name", site_id))
    return f"- [{name}]({base_url}sites/{site_id}/) ({markdown_text(site.get('country', ''))})"


def notes(index: Mapping[str, Any], versions: Mapping[str, Any], sites: Sequence[Mapping[str, Any]],
          *, commit: str | None = None, citation: Mapping[str, Any] | None = None) -> str:
    dataset = index["dataset"]
    counts = dataset["counts"]
    base = str(index["base_url"])
    identifier = dataset["id"]
    entry = next((item for item in versions.get("versions", []) if item.get("id") == identifier), {})
    by_id = {site.get("site_id"): site for site in sites}
    updated = dataset.get("updated_at", dataset["checkpoint_date"])
    start = dataset.get("observation_window_start", dataset.get("window_start"))
    end = dataset.get("observation_window_end", dataset["lifecycle_reference_date"])
    lines = [
        f"Data updated {updated}.",
        "",
        f"Status observations: {start} to {end}. Each project retains its last reported status and "
        "observation date; an Atlas update does not mean every project was rechecked.",
        "",
        f"- {counts['physical_sites']} physical sites with {counts['projects']} projects in "
        f"{counts['countries']} countries ({counts.get('non_us_sites', '?')} sites outside the United States)",
        f"- {counts['evidence']} evidence rows, each with its source URL, retrieval time, content hash, licence "
        "and attribution",
    ]
    added = list(entry.get("added_site_ids") or [])
    removed = list(entry.get("removed_site_ids") or [])
    if added or removed:
        lines += ["", "## Additions and corrections", ""]
        if added:
            lines.append(f"{len(added)} site{'s' if len(added) != 1 else ''} added:")
            lines.append("")
            lines += [_site_line(base, by_id.get(site_id), site_id) for site_id in added[:MAX_LISTED_SITES]]
            if len(added) > MAX_LISTED_SITES:
                lines.append(f"- and {len(added) - MAX_LISTED_SITES} more (see the data history)")
        if removed:
            if added:
                lines.append("")
            lines.append(f"{len(removed)} site{'s' if len(removed) != 1 else ''} removed: "
                         + ", ".join(f"`{site_id}`" for site_id in removed))
    lines += [
        "",
        f"The [data history]({base}versions/) lists additions, corrections and earlier snapshots.",
        "",
        "## Coverage and interpretation",
        "",
        *[f"- {caveat}" for caveat in CAVEATS],
        "",
        "## Files",
        "",
        f"The snapshot's downloads and checksums are listed at <{base}downloads/{identifier}/>; "
        "the zip holds every file of the snapshot, including the original data files bound by "
        "`manifest.json`. Verify downloads with `sha256sum --check --ignore-missing SHA256SUMS`. The same data is served by the "
        f"static JSON API at <{base}api/v1/>.",
        "",
        "## Licence and citation",
        "",
        "Atlas-authored data: CC BY 4.0. Geometries derived from OpenStreetMap: © OpenStreetMap contributors, "
        "ODbL 1.0. Other third-party facts, titles and URLs keep their source terms, recorded per evidence row and "
        f"in `ATTRIBUTION.txt` ([DATA_LICENSE.md]({index.get('repository_url', '')}/blob/main/DATA_LICENSE.md)).",
        "",
        (
            f"Cite as: {citation['apa']}" if citation and isinstance(citation.get("apa"), str)
            else f"Cite the dated snapshot you used ([data history]({base}versions/))."
        ),
        "",
        f"The same citation as BibTeX, RIS and CSL-JSON: <{base}api/v1/citation.json>; `CITATION.cff` in the "
        "repository has the citation metadata.",
    ]
    if commit:
        lines += ["", f"Built from commit {commit}."]
    return "\n".join(lines) + "\n"


def is_prerelease(dataset: Mapping[str, Any]) -> bool:
    """Date-based updates are releases; historical snapshots retain their archive status."""
    if dataset.get("release_status") == "published":
        return False
    return not bool(dataset.get("publishable_as_final"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a GitHub Release of the current data snapshot.")
    parser.add_argument("--site", required=True, type=Path, help="built site directory")
    parser.add_argument("--notes", required=True, type=Path, help="write the release notes (Markdown) here")
    parser.add_argument("--assets", required=True, type=Path, help="write the asset paths, one per line, here")
    parser.add_argument("--commit", help="source commit to mention in the notes")
    args = parser.parse_args(argv)
    try:
        index = _read_json(args.site / "api" / "v1" / "index.json")
        versions = _read_json(args.site / "api" / "v1" / "versions.json")
        sites = _read_json(args.site / "api" / "v1" / "sites.json")
        citation_path = args.site / "api" / "v1" / "citation.json"
        citation = _read_json(citation_path) if citation_path.is_file() else None
        dataset = index["dataset"]
        assets = asset_paths(args.site, dataset["id"])
        args.notes.write_text(
            notes(index, versions, sites, commit=args.commit, citation=citation), encoding="utf-8"
        )
        args.assets.write_text("".join(f"{path}\n" for path in assets), encoding="utf-8")
    except (ReleaseError, KeyError) as error:
        print(f"release_notes: {error}", file=sys.stderr)
        return 1
    print(release_tag(dataset["id"]))
    print(release_title(dataset))
    print("prerelease" if is_prerelease(dataset) else "release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
