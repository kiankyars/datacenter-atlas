"""Release notes, tag and asset list for a GitHub Release of the current dataset version.

The ``release`` job of ``.github/workflows/pages.yml`` (enabled by the repository variable
``ATLAS_GITHUB_RELEASES=true``) runs this on the deployed site's files, then creates the release
``data-<dataset id>`` once per version with the files listed here attached, so every checkpoint
gets an immutable, citable copy of its derived formats (and, with the Zenodo GitHub integration,
a DOI).

Usage (standard library only)::

    python3 site/e2e/release_notes.py --site _site --notes notes.md --assets assets.txt
    # prints the tag on the first line and the title on the second
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
    "Each status is the **last observed physical status** as of a dated source, not the status today.",
    "Locators place a site on the map; they are **not building footprints** or construction extents.",
    "A missing capacity, role or workload is **unknown, not zero**.",
    "The dataset is a **reviewed sample, not a census** of data-centre construction.",
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
    return f"{dataset['label']} ({dataset['id']})"


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
    final = bool(dataset.get("publishable_as_final"))
    lines = [
        f"Dataset version `{identifier}`: {dataset['label']}, checkpoint {dataset['checkpoint_date']}, "
        f"lifecycle reference date {dataset['lifecycle_reference_date']}.",
        "",
        (
            "**A final release.**" if final else
            f"**A reviewed {dataset.get('release_status', 'draft')}, not a final release**: some release gates are "
            f"not met ([release gates]({base}methodology/#release-gates))."
        ),
        "",
        f"- {counts['physical_sites']} physical sites with {counts['projects']} construction projects in "
        f"{counts['countries']} countries ({counts.get('non_us_sites', '?')} sites outside the United States)",
        f"- {counts['evidence']} evidence rows, each with its source URL, retrieval time, content hash, licence "
        "and attribution",
    ]
    added = list(entry.get("added_site_ids") or [])
    removed = list(entry.get("removed_site_ids") or [])
    if added or removed:
        lines += ["", "## Changes since the previous version", ""]
        if added:
            lines.append(f"{len(added)} site{'s' if len(added) != 1 else ''} added:")
            lines.append("")
            lines += [_site_line(base, by_id.get(site_id), site_id) for site_id in added[:MAX_LISTED_SITES]]
            if len(added) > MAX_LISTED_SITES:
                lines.append(f"- and {len(added) - MAX_LISTED_SITES} more (see the versions page)")
        if removed:
            if added:
                lines.append("")
            lines.append(f"{len(removed)} site{'s' if len(removed) != 1 else ''} removed: "
                         + ", ".join(f"`{site_id}`" for site_id in removed))
    lines += [
        "",
        f"The [versions page]({base}versions/) compares every version with the one before it.",
        "",
        "## Read before use",
        "",
        *[f"- {caveat}" for caveat in CAVEATS],
        "",
        "## Files",
        "",
        f"The attached files are the derived formats and checksums published at <{base}downloads/{identifier}/>; "
        f"the zip holds every file of the version, including the original checkpoint files bound by "
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
            else f"Cite the version you used ({base}versions/ lists every version)."
        ),
        "",
        f"The same citation as BibTeX, RIS and CSL-JSON: <{base}api/v1/citation.json>; `CITATION.cff` in the "
        "repository has the citation metadata.",
    ]
    if commit:
        lines += ["", f"Built from commit {commit}."]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a GitHub Release of the current dataset version.")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
