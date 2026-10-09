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

Published versions are frozen and never rewritten. An accepted correction is applied, and
documented, in a later checkpoint.

A status is the last authoritative observation on or before the dataset's lifecycle reference
date. News that a project finished, paused or was cancelled after that date does not make the
record wrong, but please report it: such successors are checked before the next checkpoint.

## Suggest a new site

Use the [new-site form](https://github.com/kiankyars/datacenter-atlas/issues/new?template=new-site.yml).
Suggestions enter a research queue and are reviewed against the
[selection rules](https://kiankyars.github.io/datacenter-atlas/methodology/#selection). Nothing is
added automatically, and a site may be held until its evidence is sufficient. A site needs all of
the following.

1. **Dated evidence of physical work.** A primary public source (company disclosure, government
   record, regulatory filing) stating that construction is under way on the named project: site
   preparation, civil works, foundations, shell, MEP/electrical work, general construction or
   commissioning, with the date the statement applies to. Announcements, land purchases, permits,
   grid-connection requests, groundbreaking plans and expected opening dates do not qualify by
   themselves, and a later page edit or retrieval date is not an observation date. Each checkpoint
   accepts only observations from the 90 days before its fixed lifecycle reference date.
2. **A precise locator.** A source that places the project or its campus: an official parcel or
   boundary, an official address point, a coordinate published by the developer or a public
   authority, or a named map feature. Say what it locates (a building, the project or the whole
   campus). City centres, head-office addresses and industrial-zone centroids are not accepted.
3. **A new physical site.** Search the [site list](https://kiankyars.github.io/datacenter-atlas/sites/)
   first. Another building or phase on a listed campus does not add a site.
4. **No completion or cancellation by the reference date.** If you know of a later status, include
   it.

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
python3 -m http.server -d _site 8000                     # preview at http://localhost:8000/
python3 -m unittest -v tests.test_public_site
node --test site/js-tests/*.test.mjs                     # frontend logic; no browser needed
```

The browser end-to-end tests in `site/e2e/` use Playwright and run in GitHub Actions
([`pages.yml`](.github/workflows/pages.yml)); their hash-locked tooling is pinned in
[`site/e2e/requirements.txt`](site/e2e/requirements.txt). [docs/public_site.md](docs/public_site.md)
explains how the site is built and how to run those tests yourself.

### Validate the datasets and lint

```sh
python3 scripts/build_expansion_200_draft.py --batch thirty-fifth-reviewed --validate-only
python3 -m unittest -v tests.test_verified_construction_core_v018 tests.test_expansion_200_thirty_fifth_reviewed
uv run --locked --only-group lint ruff check datacenter_atlas/public_site.py scripts/build_public_site.py tests/test_public_site.py
```

[`clean-clone.yml`](.github/workflows/clean-clone.yml) lists the full set of corpus-free tests and
lint targets that CI runs.

### Ground rules

- **Frozen data stays frozen.** Never edit files under `verified_construction_core/`,
  `definitions/`, `sources/` or `releases/` in place; manifests and tests bind their bytes. New data
  arrives as a new checkpoint directory produced by the dataset builder, and corrections are
  versioned.
- **Standard library only** for Python code, with deterministic output: the same inputs must
  produce byte-identical files.
- **Treat data as untrusted text.** Escape it in HTML, never insert it with `innerHTML`, and link
  only `http` and `https` URLs.
- **No third-party requests** from the site except basemap tiles: no analytics, web fonts or CDNs.
- **`.gitignore` is default-deny.** Only whitelisted paths are tracked. If `git status` does not
  show a new file, it needs a whitelist entry.
- Add or update tests with every behaviour change, and keep commits focused.

## Licensing of contributions

By contributing, you agree that your code is licensed under the [MIT License](LICENSE) and your
data and documentation under [CC BY 4.0](DATA_LICENSE.md), and you confirm that you have the right
to submit them. Third-party sources you cite keep their own terms; link to them rather than copying
them in.
