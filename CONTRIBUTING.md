# Contributing to Data Center Atlas

Thank you for helping. The atlas is only as good as its evidence, so the most valuable
contributions are corrections and well-sourced new sites. Code and documentation fixes are welcome
too.

## Report a correction

Use the [correction form](https://github.com/kiankyars/datacenter-atlas/issues/new?template=correction.yml).
The "Report a correction" link on every site page opens it with the site ID filled in. Include:

- the `site_id`, and the project if the site has several;
- what the record says now and what it should say;
- a public source that supports the correction, with its date.

Accepted corrections appear in the next data update. Earlier published files remain available
unchanged in the data archive.

A status is the last supported report for that project, with its own date. An Atlas update does
not renew older evidence. Sites remain listed as they are completed, open, pause, close or change
status. Please report newer evidence so their records can be updated. Correcting or removing an
unsupported record is separate from a documented change in the project's status.

## Suggest a new site

Use the [new-site form](https://github.com/kiankyars/datacenter-atlas/issues/new?template=new-site.yml).
Suggestions are checked against the
[selection criteria](https://kiankyars.github.io/datacenter-atlas/methodology/#selection). Include
the following evidence.

1. **Dated evidence for the status.** A primary public source (company disclosure, government
   record or regulatory filing) identifies the named project and supports its proposal, permit,
   physical construction, completion or operation. Record the date the evidence applies to;
   a later page edit or retrieval date does not replace it. New sites need status evidence dated
   within 90 days before the data update. Keep month-only dates in the research notes without
   inventing a day; existing records retain their dates until newer evidence supports a change.
2. **A precise locator.** A source that places the project or its campus: an official parcel or
   boundary, an official address point, a coordinate published by the developer or a public
   authority, or a named map feature. Say what it locates (a building, the project or the whole
   campus). City centres, head-office addresses and industrial-zone centroids are not accepted.
3. **A new physical site.** Search the [site list](https://kiankyars.github.io/datacenter-atlas/sites/)
   first. Another building or phase on a listed campus does not add a site.
4. **A check for later reports.** Include any later completion, opening, pause, cancellation or
   other status report. Keep the latest supported status and its date; do not infer a change from
   elapsed time or an expected opening date.

An announcement supports an announced project. A permitted status requires issued consent for
the data-centre development itself: record the authority, decision date and scope. A permit
application, utility approval, microgrid consent or air permit alone is insufficient. Construction
requires evidence of physical work. Completion and operation require their own evidence;
a completed shell or commissioning milestone does not establish operation.

A reviewed news or analyst report can support a physical status only through an explicitly
attributed firsthand statement by a named project participant. Record the speaker and role,
project identity, observation date, supported status and review. Preserve the publisher and
source kind. General analysis, forecasts and summaries do not qualify. This exception does not
establish an announcement or development consent.

Link public sources only. Please do not upload confidential documents, copies of paywalled
material or personal data.

## Work on the code or documentation

### Setup

- Python 3.11 or newer. The dataset builders and the website builder use only the standard library
  and need no network access.
- Optional: [uv](https://docs.astral.sh/uv/) for the pinned test and lint tools declared in
  `pyproject.toml` and `uv.lock`.
- Optional: Node.js 22 or newer for the frontend unit tests.

```sh
git clone https://github.com/kiankyars/datacenter-atlas.git
cd datacenter-atlas
```

### Build and test the website

```sh
python3 scripts/build_public_site.py --output _site      # add --force to rebuild over an earlier build
python3 site/e2e/check_public_metadata.py --site _site   # README, CITATION.cff and DATA_LICENSE.md agree with it
python3 site/e2e/pages_server.py --directory _site       # preview at http://127.0.0.1:8000/datacenter-atlas/
python3 -m unittest -v tests.test_public_site
node --test site/js-tests/*.test.mjs                     # frontend logic; no browser needed
```

`pages_server.py` serves the build the way GitHub Pages does (no directory listings, `404.html` for
missing paths), so a link that works there works in production. The browser end-to-end tests in
`site/e2e/` use Playwright and run in GitHub Actions ([`pages.yml`](.github/workflows/pages.yml));
their hash-locked tooling is pinned in [`site/e2e/requirements.txt`](site/e2e/requirements.txt).
[docs/public_site.md](docs/public_site.md) explains how the site is built and how to run those
tests yourself.

### Validate the datasets and lint

```sh
python3 scripts/build_dataset_update.py --input definitions/atlas-update-2026-10-13.json --validate-only
python3 -m unittest -v tests.test_dataset_update tests.test_public_site
uv run --locked --only-group lint ruff check datacenter_atlas/public_site.py scripts/build_public_site.py tests/test_public_site.py
```

[`clean-clone.yml`](.github/workflows/clean-clone.yml) lists the full set of corpus-free tests and
lint targets that CI runs.

### Publish a data update

Research in this order: **United States → China → United Kingdom → Germany → Japan**, with bounded
assignments recorded in [country research](docs/country_research.md). Each pass adds missing sites
and reviews existing ones across all statuses. Keep compact source projections under `sources/`
and a dated change list under `definitions/`. Each change identifies its source, observation
date, site identity and later-status check. Pin the source files and base manifest by SHA-256.

`scripts/build_dataset_update.py --input definitions/atlas-update-YYYY-MM-DD.json` builds a new
dated directory. Use `--validate-only` to reproduce and compare it, then select that directory
in `site/config.json`. Build the website and run the metadata check with `--write` to refresh
citation and attribution metadata. Keep dataset counts and update dates out of the README.

### Code layout

Implementations live in `datacenter_atlas/`; command-line entry points live in `scripts/`.
The root `__init__.py` provides imports from the repository parent without per-module wrappers.
The remaining root wrappers preserve files whose paths and bytes are checked by historical
builders and manifests, plus an executable enrichment entry point. Do not add new ones.

### Ground rules

- **Preserve published data.** Never edit files under `verified_construction_core/`,
  `definitions/`, `sources/` or `releases/` in place; manifests and tests bind their bytes. Additions
  and corrections go into a new data directory produced by the dataset builder, keeping earlier
  files available for reproducibility.
- **Standard library only** for Python code, with deterministic output: the same inputs must
  produce byte-identical files.
- **Treat data as untrusted text.** Escape it in HTML, never insert it with `innerHTML`, and link
  only `http` and `https` URLs.
- **No third-party requests** from the site except basemap tiles: no analytics, web fonts or CDNs.
- **`.gitignore` is default-deny.** Only whitelisted paths are tracked. If `git status` does not
  show a new file, it needs a whitelist entry. Every dataset directory may hold the manifest-listed
  file names, including `review-provenance.json`, `source-records.json` and `identity-mapping.json`;
  `python3 scripts/check_tracked_dataset_files.py` fails when Git does not track a file a dataset
  manifest lists.
- Add or update tests with every behaviour change, and keep commits focused.

## Licensing of contributions

By contributing, you agree that your code is licensed under the [MIT License](LICENSE) and your
data and documentation under [CC BY 4.0](DATA_LICENSE.md), and you confirm that you have the right
to submit them. Third-party sources you cite keep their own terms; link to them rather than copying
them in.
