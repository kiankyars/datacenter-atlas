# Public site: maintainer notes

The public site at <https://kiankyars.github.io/datacenter-atlas/> is a static website, JSON API and
download area generated from tracked files by [`scripts/build_public_site.py`](../scripts/build_public_site.py)
(module [`datacenter_atlas/public_site.py`](../datacenter_atlas/public_site.py)). The builder uses
only the Python standard library (3.11 or newer), makes no network requests and is deterministic:
the same inputs produce a byte-identical `_site/`. One caveat: the derived `atlas.sqlite` and the
zip archives also depend on the SQLite and zlib libraries, so a CI runner image update can in
principle change their bytes (and their published checksums). The builder zeroes the SQLite
header field that records the writing library's version, so a routine SQLite upgrade alone does
not; a change in SQLite's page layout or in zlib's compression would. The original checkpoint
files are copied verbatim and never change. The output is ignored by Git and deployed by GitHub
Actions.

This page is for maintainers. Users should start with the [README](../README.md) and the
[methodology](https://kiankyars.github.io/datacenter-atlas/methodology/).

## Inputs

| Path | Role |
| --- | --- |
| [`site/config.json`](../site/config.json) | Site name, tagline, base URL, repository and issue URLs, `versions_root`, `current_dataset`, `last_preview_dataset`, `status_window_days`, author and licence metadata |
| `verified_construction_core/*/` | Every direct child containing a `manifest.json` is a dataset version, and every version is published |
| `site/content/*.html` | Prose fragments for the methodology and about pages |
| `site/templates/explorer.html` | Markup for the map explorer at `/` |
| `site/static/` | Copied verbatim to the output root: CSS, JavaScript, vendored Leaflet 1.9.4, favicon |
| `site/vocabulary.json` | Labels and descriptions for coded values (statuses, scopes, metrics and so on) |
| `site/field_descriptions.json` | Data-dictionary text; every column of the current schema needs an entry |

Before writing anything, the builder validates every dataset it publishes. Each file listed in a
version's `manifest.json` must match its recorded byte count and SHA-256, and `manifest.sha256`
must match `manifest.json`. Any mismatch stops the build with an error.

## Build

```sh
python3 scripts/build_public_site.py --output _site
```

| Option | Meaning |
| --- | --- |
| `--output DIR` | Output directory. A non-empty directory is refused. |
| `--force` | Replace an existing output directory, but only one containing the `.atlas-site` marker that a previous build wrote. |
| `--base-url URL` | Absolute base URL for JSON, the feed, the sitemap and canonical links. Defaults to `base_url` in `site/config.json`. HTML pages always link relatively. |
| `--source-commit SHA` | Commit shown in the footer and in `api/v1/index.json`. CI passes `$GITHUB_SHA`; local builds without it say "local build". |
| `--config PATH` | Use another config file instead of `site/config.json`. |

The builder writes into a staging directory beside the output and moves it into place only when
the build succeeds. It refuses to write into the repository root, `site/`,
`verified_construction_core/` or `.git`. `build_site()` in `datacenter_atlas/public_site.py` is the
programmatic entry point and returns a summary of what it wrote.

## Preview locally

```sh
python3 -m http.server -d _site 8000   # http://localhost:8000/
```

Internal links are relative, so the same output works at a server root, under the production
sub-path and in CI. To reproduce the production sub-path, as the end-to-end tests do:

```sh
mkdir -p serve && cp -R _site serve/datacenter-atlas
python3 -m http.server -d serve 8000   # http://localhost:8000/datacenter-atlas/
```

`404.html` is the one exception to relative linking: GitHub Pages serves it for any missing path,
so its links are absolute URLs built from the base URL and point at production in a local preview.

## Output

```text
index.html                         map explorer (map, list, filters, detail drawer)
sites/index.html                   static table of all sites (works without JavaScript)
sites/<site_id>/index.html         one page per site
countries/index.html               countries with counts
countries/<iso2>/index.html        one page per country (lower-case ISO code)
data/index.html                    downloads, checksums, usage recipes, licence, citation
data/dictionary/index.html         field dictionary and coded values
api/index.html                     API documentation with examples
methodology/index.html             selection rules, statuses, locators, release gates, limits
versions/index.html                every dataset version and the sites each one added
about/index.html                   about, licence, citation, corrections, legal notices
about/attribution/index.html       the current ATTRIBUTION.txt, linkified, and required notices
404.html  feed.xml  sitemap.xml  robots.txt  .nojekyll  favicon.svg  assets/
api/v1/index.json                  API root: dataset, endpoints, downloads, licences, build
api/v1/sites.json                  site summaries
api/v1/sites.geojson               FeatureCollection of site summaries (used by the explorer)
api/v1/sites/<site_id>.json        one site with its projects and evidence
api/v1/projects.json               all projects; api/v1/projects/<project_id>.json each
api/v1/evidence.json               all evidence; api/v1/evidence/<evidence_id>.json each
api/v1/countries.json              country summaries; api/v1/countries/<ISO2>.json each
api/v1/stats.json                  aggregate counts and release gates
api/v1/versions.json               every dataset version
api/v1/vocabularies.json           labels and descriptions for coded values
downloads/latest/                  current version: original files plus derived formats
downloads/<dataset_id>/            every version, byte-identical originals plus SHA256SUMS
```

`downloads/<current id>/` and `downloads/latest/` hold the same bytes, except that the zip is named
`datacenter-atlas-<id>.zip` in the pinned directory and `datacenter-atlas-latest.zip` in `latest/`.
The derived formats are `atlas.json`, `sites.ndjson`, `projects.ndjson`, `evidence.ndjson`,
`atlas.sqlite`, `sites.kml`, `datapackage.json` and the zip. Each directory's `SHA256SUMS` lists
every other file in that directory (including the zip) in GNU format. The zip is deterministic:
sorted entries, fixed timestamps and fixed permissions.

### Typed JSON

JSON, NDJSON and the API convert each CSV value using the logical types in the version's
`schema.json`:

- an empty string becomes `null`, whatever the type;
- `number` becomes a float, `integer` an int, and `boolean` (`true` or `false`) a bool;
- `json_array` and `geojson_geometry` are parsed;
- everything else stays a string, including unknown future types.

Typed JSON drops a trailing `_json` from field names (`statuses_json` becomes `statuses`), and keeps
the column order. CSV and SQLite keep the original names. Derived fields are appended after the
original ones: for sites `official_boundary`, `country_slug`, `url` and `api_url`; for projects
`evidence_ids`, `status_source`, `url` and `api_url`; for evidence `site_ids` and `url`. JSON uses
absolute URLs; HTML links are relative. Keys follow a fixed documented order, and files are UTF-8
with a trailing newline.

## Page content and templates

`site/content/*.html` and `site/templates/explorer.html` are HTML fragments without `<html>`,
`<head>` or `<body>`; the builder wraps them in the shared layout. A content page starts with one
`<h1>`, followed by `<h2>` sections that carry `id` attributes. The methodology page must contain
`id="release-gates"` (a `<section id="release-gates">`) and use the `{{{gates_table}}}` token, or
the build fails.

Tokens:

- `{{name}}` inserts HTML-escaped text and `{{{name}}}` inserts HTML generated by the builder.
  Using a text token in triple braces, or an HTML token in double braces, is a build error.
- An unknown token is a build error. Available: `{{root}}`, `{{site_name}}`, `{{tagline}}`,
  `{{base_url}}`, `{{repository_url}}`, `{{issues_url}}`, `{{dataset.id}}`, `{{dataset.label}}`,
  `{{dataset.release_status}}`, `{{dataset.checkpoint_date}}`, `{{dataset.checkpoint_year}}`,
  `{{dataset.lifecycle_reference_date}}`, `{{dataset.status_window_days}}`,
  `{{dataset.window_start}}`, `{{counts.physical_sites}}`, `{{counts.projects}}`,
  `{{counts.countries}}`, `{{counts.evidence}}`, `{{counts.non_us_sites}}`,
  `{{counts.official_boundary_projects}}`, `{{counts.polygon_sites}}`,
  `{{counts.power_observation_projects}}`, `{{last_preview.label}}`,
  `{{last_preview.counts.physical_sites}}`, `{{versions.count}}`, `{{build.commit_short}}`,
  `{{{gates_table}}}` and `{{{status_legend}}}`. Every other key of the current manifest's
  `counts` object is also available as `{{counts.<key>}}`.
- HTML comments (`<!-- ... -->`) are removed before tokens are replaced, so they never reach the
  site and tokens inside them are ignored.
- A literal `{{` left after token replacement is a build error; a lone `}}` is accepted, but avoid
  both in prose. In BibTeX, for example, delimit fields with quotes rather than braces next to a
  token: `{` followed by `{{dataset.id}}` reads as `{{{dataset.id}}}`.

Markup rules:

- Use only the CSS classes the stylesheet defines: `page`, `page-wide`, `lede`, `muted`, `small`,
  `mono`, `breadcrumbs`, `stats`, `stat`, `stat-value`, `stat-label`, `badge`, `status-<code>`,
  `tag`, `btn`, `btn-primary`, `btn-small`, `card`, `cards`, `grid-2`, `kv`, `table-wrap`,
  `data-table`, `num`, `callout`, `callout-warning`, `code`, `copy-btn`, `toc`, `download-list`,
  `checksum`, `site-map`, `evidence-list`, `project`, `filter-input`, `sortable`,
  `hidden-noscript`, `external` and `anchor`.
- Link internal pages through `{{root}}`, for example `{{root}}data/`. Give external links
  `class="external" rel="noopener"`, without `target`. Only `http` and `https` URLs are allowed.
- The Content-Security-Policy forbids inline scripts, inline `style` attributes and inline event
  handlers. Scripts are external files under `assets/`, and data for scripts goes in
  `<script type="application/json">` blocks written by the builder.
- A copy button is `<button type="button" class="copy-btn hidden-noscript" data-copy="...">`, with
  the escaped text to copy in the attribute. `hidden-noscript` keeps it hidden until `site.js` runs,
  because without JavaScript the button cannot copy anything.

## Security and privacy

- Every dataset value is untrusted text. Python templates escape it with
  `html.escape(..., quote=True)`; JavaScript uses `textContent` and `setAttribute`, never
  `innerHTML` with data; and only `http` and `https` values become links.
- Every page carries a restrictive Content-Security-Policy. The only third-party requests are
  basemap tiles (CARTO, OpenStreetMap and EOX): no analytics, fonts or CDNs.
- Local storage holds per-browser conveniences only, such as the basemap choice.

## API versioning policy

- The API is versioned by path (`/api/v1/`). `index.json` and the other object responses (site,
  country, stats, versions and vocabularies documents) carry `"api_version": "1"`.
- Within v1, changes are additive only: new endpoints, new fields appended to existing objects,
  new codes in vocabularies and new dataset versions. Existing fields are not removed, renamed,
  retyped or given a new meaning.
- A breaking change needs a new path, `/api/v2/`, published alongside v1; v1 is not changed in
  place.
- Clients should ignore fields they do not know.
- The API always serves the current dataset, so values change at each checkpoint. Check
  `dataset.id` in responses, or use `downloads/<dataset_id>/`, for a snapshot that never changes.

## Making a new checkpoint current

1. Produce the new version directory under `verified_construction_core/` with the dataset pipeline
   (see [expansion_200.md](expansion_200.md)), with its contract, tests and a passing
   `--validate-only` run. Never modify an existing version.
2. Make sure Git tracks every file its manifest lists. `.gitignore` is default-deny, and
   `review-provenance.json` is whitelisted one directory at a time.
3. Set `current_dataset` in `site/config.json` to the new directory, and `last_preview_dataset` as
   well if the new version is a preview.
4. Add `site/field_descriptions.json` entries for any new columns and `site/vocabulary.json`
   entries for any new codes; `tests/test_public_site.py` fails otherwise.
5. Update the facts written outside the build: the counts, gates table, version, citation year and
   commands in `README.md`; `version`, `date-released` and `abstract` in `CITATION.cff`; the
   example version and the OpenStreetMap geometry count in `DATA_LICENSE.md`; and any
   checkpoint-specific statements in `site/content/methodology.html`. Pages built from
   `site/content/` take counts, dates and the citation year from tokens.
6. Rebuild, run the tests, then commit and push to `main`. CI deploys the site;
   `downloads/<previous id>/` stays where it is and `downloads/latest/` moves to the new version.

## Tests

```sh
python3 -m unittest -v tests.test_public_site   # offline; builds once into a temporary directory
node --test site/js-tests/*.test.mjs            # pure frontend logic, no browser (Node 22 or newer)
```

The unit tests check, among other things, manifest validation, counts, typed conversion, that
every site has a page and a JSON document, SQLite keys, checksums, the zip, the Data Package, KML,
internal links, escaping, deterministic rebuilds, unknown tokens, dictionary coverage and the
Content-Security-Policy. CI runs the same module from the directory above the checkout, as
`python -m unittest -v datacenter_atlas.tests.test_public_site`.

The browser end-to-end tests in `site/e2e/` use Playwright. They run in CI, block every non-local
request (basemap tiles get a blank image), read their expected counts from `api/v1/index.json`
and save screenshots to `site-screenshots/`. The pinned, hash-locked tooling (Playwright, pytest
and axe-playwright-python) is listed in
[`site/e2e/requirements.txt`](../site/e2e/requirements.txt). Running the tests locally downloads
a browser:

```sh
python3 -m pip install --require-hashes --only-binary :all: -r site/e2e/requirements.txt
python3 -m playwright install chromium
python3 scripts/build_public_site.py --output _site --force
python3 -m pytest site/e2e -q
```

Without `ATLAS_BASE_URL`, the tests serve `_site/` (or `$ATLAS_SITE_DIR`) themselves under the
`/datacenter-atlas/` sub-path on an ephemeral 127.0.0.1 port. Environment variables:

| Variable | Meaning |
| --- | --- |
| `ATLAS_BASE_URL` | Test an already running server instead, for example `http://127.0.0.1:8000/datacenter-atlas/` |
| `ATLAS_SITE_DIR` | Built site to serve when `ATLAS_BASE_URL` is unset (default `_site/`) |
| `ATLAS_SCREENSHOT_DIR` | Where screenshots go (default `site-screenshots/`) |
| `ATLAS_E2E_REQUIRED` | `1` turns every skip (no Playwright, no built site) into an error; CI sets it |

Without Playwright the browser tests skip; the API, download and 404 checks still run when a
built site is available.

## CI and deployment

- [`.github/workflows/pages.yml`](../.github/workflows/pages.yml) (workflow "Public site") runs on
  pushes to `main`, on pull requests and on manual dispatch. The `build` job (permissions:
  `contents: read`, `pages: read`) builds the site with the production base URL and
  `--source-commit "$GITHUB_SHA"`, runs the unit tests and the JavaScript tests (it fails if
  `site/js-tests/` has no `*.test.mjs` files), and then the Playwright tests against a copy served
  under `/datacenter-atlas/`. It always uploads the `site-screenshots` artifact. On pushes to
  `main` it uploads `_site` as the Pages artifact before the browser tooling is installed, so
  nothing that tooling downloads can alter what is deployed.
- The `deploy` job (permissions: `pages: write`, `id-token: write`) runs only for pushes to `main`,
  after the whole `build` job has passed, and publishes with `actions/deploy-pages` to the
  `github-pages` environment. Deployments share the `pages` concurrency group and do not cancel
  each other; a newer push to a pull request cancels that pull request's older run.
- [`.github/workflows/clean-clone.yml`](../.github/workflows/clean-clone.yml) also builds the site
  into a temporary directory and runs `tests.test_public_site` and `ruff` on the builder.
- One-time repository setting: Settings, Pages, Build and deployment, Source: **GitHub Actions**.
- To roll back, revert the offending commit on `main`; the next push redeploys.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Manifest or checksum mismatch | A tracked dataset file changed. Restore it from Git; never edit a manifest to match. |
| Unknown template token | Correct the token in `site/content/` or `site/templates/` using the list above. |
| Output directory is not empty | Choose a new directory, or pass `--force` to replace an earlier build. |
| A column has no dictionary description | Add it to `site/field_descriptions.json`. |
| `site/static/... is missing` or an output path is written twice | Restore the asset the page layout needs (`assets/site.css`, `site.js`, `site-map.js`, `app.js`, the vendored Leaflet files, `favicon.svg`), or rename a static file that collides with a generated path such as `api/` or `downloads/`. |
| The live site is not updated | Check that the `deploy` job ran for the push to `main` and that Pages uses GitHub Actions as its source. |
