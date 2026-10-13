# Public site: maintainer notes

The public site at <https://kiankyars.github.io/datacenter-atlas/> is a static website, JSON API and
download area generated from tracked files by [`scripts/build_public_site.py`](../scripts/build_public_site.py)
(module [`datacenter_atlas/public_site.py`](../datacenter_atlas/public_site.py)). The builder uses
only the Python standard library (3.11 or newer), makes no network requests and is deterministic:
the same inputs produce a byte-identical `_site/`. One caveat: the derived `atlas.sqlite` and the
zip archives also depend on the SQLite and zlib libraries. The builder writes `atlas.sqlite` with
`PRAGMA secure_delete = ON`, a fixed page size and the header field that records the writing
library's version zeroed, so it does not depend on the defaults a particular SQLite build was
compiled with; a future SQLite or zlib whose file layout or compression differs could still change
those bytes (and their published checksums). The archived source data files are copied verbatim
and never change. The output is ignored by Git and deployed by GitHub Actions.

This page is for maintainers. Users should start with the [README](../README.md) and the
[methodology](https://kiankyars.github.io/datacenter-atlas/methodology/).

Date-based updates use a `YYYY-MM-DD` directory and manifest format
`datacenter-atlas-update-v1`, with `release_status: published`. `updated_at` is the archive date;
`observation_window_start` and `observation_window_end` are the actual earliest and latest
project `status_as_of` dates. Existing rows retain their observation dates. Their
`status_age_days_at_review` is recalculated against the update date. The public builder checks
these dates against every project and sorts these updates chronologically after the historical
archives. Historical snapshots retain their original date semantics and bytes.

The API adds `updated_at`, `observation_window_start` and `observation_window_end` to dataset
references. For published updates, `status_window_days` measures the observation span, rather
than imposing an age limit. It retains its original meaning for historical snapshots.

Project records cover announcements, granted development permits, construction and subsequent
completion or operation. Existing sites keep their identifiers and URLs when their status changes.
The legacy CSV/API field `last_observed_physical_status` now carries this project status;
`announced` and `permitted` do not assert physical work, and `completed` does not assert operation.
Each change retains its dated source and earlier evidence. See
[country research](country_research.md) for the agreed research order and admission rules.

## Inputs

| Path | Role |
| --- | --- |
| [`site/config.json`](../site/config.json) | Site name, tagline, base URL, repository and issue URLs, `versions_root`, `current_dataset`, `last_preview_dataset`, `status_window_days`, author and licence metadata. Optional: `first_published_dataset` (see [Download directories](#download-directories)) and `dataset_title` (the title used in citations). |
| `verified_construction_core/*/` | Every direct child containing a `manifest.json` is a dataset version, and every version is published |
| `site/content/*.html` | Prose fragments for the methodology and about pages |
| `site/templates/explorer.html` | Markup for the map explorer at `/` |
| `site/static/` | Copied verbatim to the output root: CSS, JavaScript, vendored Leaflet 1.9.4, favicon |
| `site/vocabulary.json` | Labels and descriptions for coded values (statuses, scopes, metrics and so on) |
| `site/field_descriptions.json` | Data-dictionary text; every column of the current schema needs an entry |

Before writing anything, the builder validates every dataset it publishes. Each file listed in a
version's `manifest.json` must match its recorded byte count and SHA-256, and `manifest.sha256`
must match `manifest.json`. Any mismatch stops the build with an error. The builder reads its
inputs only from manifest-listed regular files and re-checks their size and digest on every read.

## Build

```sh
python3 scripts/build_public_site.py --output _site
```

| Option | Meaning |
| --- | --- |
| `--output DIR` | Output directory. A non-empty directory is refused. |
| `--force` | Replace an existing output directory, but only one containing the `.atlas-site` marker that a previous build wrote. |
| `--base-url URL` | Absolute base URL for JSON, the feeds, the sitemap, `llms.txt` and canonical links. Defaults to `base_url` in `site/config.json`. HTML pages always link relatively. |
| `--source-commit SHA` | Commit shown in the footer and in `api/v1/index.json`. CI passes `$GITHUB_SHA`; local builds without it say "local build". |
| `--config PATH` | Use another config file instead of `site/config.json`. |

The builder writes into a staging directory beside the output and moves it into place only when
the build succeeds. It refuses to write into the repository root, `site/`,
`verified_construction_core/` or `.git`. `build_site()` in `datacenter_atlas/public_site.py` is the
programmatic entry point and returns a summary of what it wrote.

## Preview locally

```sh
python3 site/e2e/pages_server.py --directory _site --port 8000   # http://127.0.0.1:8000/datacenter-atlas/
```

[`site/e2e/pages_server.py`](../site/e2e/pages_server.py) (standard library only) serves the build
the way GitHub Pages serves this project site: only under the `/datacenter-atlas/` sub-path, a
directory URL answers with its `index.html` or `index.json` and never with a generated listing, a
directory URL without its trailing slash is redirected, a missing path gets the site's `404.html`
with status 404, and every response carries `Access-Control-Allow-Origin: *` and the media types
GitHub sends. A URL that works there also works in production. `python3 -m http.server -d _site 8000`
also works for a quick look, but it lists directories that GitHub Pages answers with 404.

Internal links are relative, so the same output works at a server root, under the production
sub-path and in CI. `404.html` is the one exception: GitHub Pages serves it for any missing path, so
its links are absolute URLs built from the base URL and point at production in a local preview.

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
methodology/index.html             selection criteria, statuses, location precision, sources, updates
versions/index.html                every dataset version and what each one changed
versions/<dataset_id>/index.html   one page per version
about/index.html                   about, licence, citation, corrections, legal notices
about/attribution/index.html       the current ATTRIBUTION.txt, linkified, and required notices
llms.txt                           entry point for language models and agents (llmstxt.org)
llms-full.txt                      methodology, field dictionary and vocabularies as one text file
feed.xml  sites-feed.xml           Atom feeds of new versions and of newly added sites
404.html  sitemap.xml  robots.txt  og-image.png  .nojekyll  favicon.svg  assets/
api/v1/index.json                  API root: dataset, endpoints, downloads, licences, caveats, build
api/v1/openapi.json                OpenAPI 3.1 description of every endpoint
api/v1/schemas/                    JSON Schemas of every response and record type (index.json lists them)
api/v1/sites.json                  site summaries
api/v1/sites.geojson               FeatureCollection of site summaries (used by the explorer)
api/v1/sites/<site_id>.json        one site with its projects and evidence (also .geojson)
api/v1/projects.json               all projects; api/v1/projects/<project_id>.json each
api/v1/evidence.json               all evidence; api/v1/evidence/<evidence_id>.json each
api/v1/countries.json              country summaries; api/v1/countries/<ISO2>.json, .geojson and .csv each
api/v1/stats.json                  aggregate counts (each map states its unit); legacy gate metadata
api/v1/versions.json               every dataset version, its files and its changes
api/v1/vocabularies.json           labels and descriptions for coded values
api/v1/citation.json               the citation as APA, BibTeX, biblatex, RIS and CSL-JSON (also citation.bib, citation.ris)
downloads/index.html               every download directory
downloads/latest/                  current version: original files, derived formats, SHA256SUMS, index.html
downloads/<dataset_id>/            every version: byte-identical originals, SHA256SUMS, index.html
```

### Download directories

`downloads/<id>/` holds a version's original files byte for byte, a `SHA256SUMS` and an
`index.html` landing page that lists every file with its size and checksum (GitHub Pages serves a
directory URL only through its `index.html`, so citations and API links to `downloads/<id>/`
resolve). Every version from the first one the live site published as current
(`FIRST_PUBLISHED_DATASET` in the builder, `2026-08-20-v0.18-draft-thirty-fifth-reviewed`, or
`first_published_dataset` in the config) up to the current one also keeps its derived formats
and its zip, `datacenter-atlas-<id>.zip`, built from that version alone. So a formerly current
version's files never disappear when a newer checkpoint becomes current. Earlier versions were
never published with derived formats and have only their originals.

`downloads/latest/` repeats the current version, with the zip named `datacenter-atlas-latest.zip`.
The derived formats are `atlas.json`, `sites.ndjson`, `projects.ndjson`, `evidence.ndjson`,
`atlas.sqlite`, `atlas.xlsx`, `sites.kml`, `datapackage.json` and the zip. Each directory's
`SHA256SUMS` lists every other data file in that directory (including the zip, not the landing
page) in GNU format. The zip is deterministic: sorted entries, fixed timestamps and fixed
permissions.

Only the original files are immutable. The derived formats are rebuilt by every build, so an
additive builder change (a new column, sheet or table) changes their bytes and checksums; users
verify them against the current `SHA256SUMS`, and the README, `CITATION.cff` and the about page say
so. A frozen copy of each version's derived formats is what the GitHub Release of that version is
for (see [CI and deployment](#ci-and-deployment)).

### Typed JSON

JSON, NDJSON and the API convert each CSV value using the logical types in the version's
`schema.json`:

- an empty string becomes `null`, whatever the type;
- `number` becomes a float, `integer` an int, and `boolean` (`true` or `false`) a bool;
- `json_array` and `geojson_geometry` are parsed;
- everything else stays a string, including unknown future types.

Typed JSON drops a trailing `_json` from field names (`statuses_json` becomes `statuses`), and keeps
the column order. CSV and SQLite keep the original names. Derived fields are appended after the
original ones: for sites `official_boundary`, `country_slug`, `url`, `api_url`,
`geometry_licenses` and `geometry_attributions`; for projects `evidence_ids`, `status_source`,
`url`, `api_url` and `geometry_source`; for evidence `site_ids`, `url`, `api_url` and
`archive_url`. JSON uses absolute URLs; HTML links are relative. Keys follow a fixed documented
order, and files are UTF-8 with a trailing newline. The API's GeoJSON follows the RFC 7946 winding
order; each version's original `sites.geojson` stays exactly as it was frozen.

## Explorer links and exports

The explorer keeps its whole view in the URL, so a copied link (or the "Copy link" button)
reproduces it. Parameters, all optional, in the order the explorer writes them:

| Parameter | Values | Meaning |
| --- | --- | --- |
| `q` | text, at most 200 characters | Search. Case, accents and apostrophes are ignored, punctuation separates words, and every word must start a word of the site name, country, ISO code, project names, status publishers or site ID (`frank` finds Frankfurt; `us` does not find campus). Chinese, Japanese and Korean words match anywhere. |
| `country` | ISO 3166-1 alpha-2 code, any case | Sites in that country. |
| `status` | comma-separated status codes, or the parameter repeated | Sites with at least one project whose last observed status is one of the codes (codes in [`vocabularies.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/vocabularies.json)). |
| `locator` | `any` (default), `official_boundary`, `polygon`, `point` | Sites with an official site boundary, with a Polygon or MultiPolygon locator, or with a point locator. |
| `power` | `1` (or `true`) | Sites with at least one typed power observation. |
| `from`, `to` | `YYYY-MM`, inclusive | Sites with a project whose `status_as_of` falls in the range. With `status`, the same project must have both the status and a date in the range. |
| `sort` | `name` (default), `country`, `newest`, `oldest`, `projects` | List order: by name, by country then name, by newest or oldest status date, or by number of projects. |
| `#site=<site_id>` | a site ID, in the fragment | Opens that site's detail drawer; an ID that is not in the current dataset shows a note instead. |

Values that are malformed (an unknown `locator` or `sort`, a country code that is not two letters, a
month that is not `YYYY-MM`) are ignored. Well-formed values are kept even when they match nothing:
a country or status that is not in the current dataset, a `from` after the last month or a `to`
before the first, shows an empty result with a note, never other sites. A reversed `from`/`to` pair
is swapped, and a bound that excludes nothing (a `from` before the first month of the data, a `to`
after the last) is dropped. Unknown values in the data never match a filter: a site with no typed
power observation is not a "0 MW" site, it is simply not matched by `power=1`.

Examples:

- <https://kiankyars.github.io/datacenter-atlas/?country=AU&status=mep_electrical,shell>:
  Australian sites last observed at the MEP/electrical or shell stage.
- <https://kiankyars.github.io/datacenter-atlas/?locator=official_boundary&sort=newest#site=vcc-site-5973ad6c7ce7afc4f6b6>:
  sites with an official boundary, newest first, with Green Mountain Undheim's details open.

The CSV and GeoJSON buttons export the sites currently listed:

- **CSV** (`datacenter-atlas-<dataset id>-sites[-filtered].csv`, UTF-8 with a byte-order mark,
  CRLF line endings, RFC 4180 quoting): the columns of the published per-country files
  (`api/v1/countries/<ISO2>.csv`), namely `site_id`, `name`, `country`, `country_iso_a2`, `latitude`,
  `longitude`, `statuses_json`, `newest_status_as_of`, `oldest_status_as_of`, `project_count`,
  `official_boundary`, `geometry_type`, `status_publishers_json`, `geometry_licenses_json`, `url` and
  `api_url`, followed by `dataset_id`. `*_json` cells hold compact JSON arrays, an empty cell is
  unknown, and text that a spreadsheet would run as a formula is prefixed with an apostrophe.
- **GeoJSON** (`.geojson`): a FeatureCollection of the listed sites' summaries, each feature with
  `id` set to the site ID and the site's full geometry. Top-level members say what the file is and
  how it may be reused: `dataset` (`id`, `label`, `release_status`), `query` (the explorer query
  string), `license`, `attribution`, `attribution_url`, `source_url` (the complete
  `api/v1/sites.geojson`), `view_url` (the exported view) and `caveats`.

In browsers that offer [WebMCP](https://github.com/webmachinelearning/webmcp)
(`document.modelContext` or `navigator.modelContext`), the explorer also registers three read-only
tools for browser agents, all annotated `readOnlyHint` and `untrustedContentHint` (titles,
publishers and notes are third-party text). They change only the view, never data, and are
unregistered when the page is left:

- `search_datacenter_sites`: filters the explorer like the URL parameters above, with the options
  `query`, `country`, `statuses`, `locator`, `has_power`, `from`, `to`, `sort` and `limit`; it
  shows the result on the page and returns site summaries with their page, API and view URLs;
- `get_datacenter_site` (`site_id`): opens the site's drawer and returns its full
  `api/v1/sites/<site_id>.json` document;
- `get_datacenter_dataset_info` (no options): dataset dates, counts, licence and attribution, API endpoints and bulk downloads with their SHA-256.

Each result repeats the data caveats. Invalid input is rejected with a reason; elsewhere nothing is
registered and the explorer works as usual.

## Page content and templates

`site/content/*.html` and `site/templates/explorer.html` are HTML fragments without `<html>`,
`<head>` or `<body>`; the builder wraps them in the shared layout. A content page starts with one
`<h1>`, followed by `<h2>` sections that carry `id` attributes. Public copy should describe the
data and how to use it. Keep internal snapshot names, review milestones and historical release
gates out of navigation, introductions and instructions.

Tokens:

- `{{name}}` inserts HTML-escaped text and `{{{name}}}` inserts HTML generated by the builder.
  Using a text token in triple braces, or an HTML token in double braces, is a build error.
- An unknown token is a build error. Available: `{{root}}`, `{{site_name}}`, `{{tagline}}`,
  `{{base_url}}`, `{{repository_url}}`, `{{issues_url}}`, `{{dataset.id}}`, `{{dataset.label}}`,
  `{{dataset.title}}`, `{{dataset.release_status}}`, `{{dataset.checkpoint_date}}`,
  `{{dataset.checkpoint_year}}`, `{{dataset.lifecycle_reference_date}}`,
  `{{dataset.status_window_days}}`, `{{dataset.window_start}}`, `{{dataset.window_end}}`, `{{counts.physical_sites}}`,
  `{{counts.projects}}`, `{{counts.countries}}`, `{{counts.evidence}}`, `{{counts.non_us_sites}}`,
  `{{counts.official_boundary_projects}}`, `{{counts.polygon_sites}}`,
  `{{counts.power_observation_projects}}`, `{{last_preview.label}}`,
  `{{last_preview.counts.physical_sites}}`, `{{versions.count}}`, `{{build.commit_short}}`,
  `{{citation.apa}}`, `{{citation.bibtex}}`, `{{{gates_table}}}`, `{{{status_legend}}}`,
  `{{{citation_block}}}` (the citation with copy buttons and links to the citation files) and
  `{{{legal_notice}}}`. Every other key of the current manifest's `counts` object is also
  available as `{{counts.<key>}}`.
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
- Every generated page carries a restrictive Content-Security-Policy in a `<meta>` tag. The
  original `map.html` files of the v0.1-v0.17 previews under `downloads/` are published byte for
  byte without one; they load nothing from other sites, and the builder publishes an original HTML,
  SVG, XML or JavaScript file only when its SHA-256 is on a reviewed allowlist
  (`REVIEWED_ACTIVE_ORIGINALS`). The only third-party requests are basemap tiles (OpenStreetMap,
  EOX and, when the site is configured with a CARTO key, CARTO): no analytics, fonts or CDNs.
- **Shared origin.** GitHub Pages serves every project site of the account from
  `https://kiankyars.github.io`, so the atlas shares its origin, and therefore `'self'` in the
  Content-Security-Policy and its `localStorage`, with the account's other Pages sites. A script on
  any of them could open or frame an atlas page and change it in the reader's browser. GitHub Pages
  cannot send response headers, and a `<meta>` policy cannot set `frame-ancestors`, so the site has
  no `frame-ancestors`, `X-Frame-Options` or `X-Content-Type-Options: nosniff`. Mitigations: the site
  stores nothing sensitive, every download is listed with its SHA-256 (in `SHA256SUMS`, the API and
  the GitHub Release), and checksums should be checked against `api/v1/index.json` or a release
  rather than against the page that offers the file. The robust fix is a dedicated origin: a custom
  domain for this repository (Settings, Pages, Custom domain, with HTTPS enforced), after which
  `base_url` in `site/config.json` and `SITE_URL` in `pages.yml` change to the new URL.
- **CI supply chain.** Every action in the workflows is pinned to a full commit SHA, with the release
  in a comment; a moved tag cannot change what builds or deploys the site. `actions/upload-pages-artifact`
  still calls `actions/upload-artifact@v4` by tag internally. The build installs the browser-test
  tooling only after the Pages artifact is captured, from a hash-locked requirements file.
- Local storage holds per-browser conveniences only, such as the basemap choice.

## API versioning policy

- The API is versioned by path (`/api/v1/`). `index.json` and the other object responses (site,
  country, stats, versions, vocabularies and citation documents) carry `"api_version": "1"`.
- `api/v1/openapi.json` (OpenAPI 3.1) describes every endpoint, and `api/v1/schemas/` holds a JSON
  Schema for every response and record type. Both change with the API, under the same rules.
- Within v1, changes are additive only: new endpoints, new fields appended to existing objects,
  new codes in vocabularies and new dataset versions. Existing fields are not removed, renamed,
  retyped or given a new meaning.
- A breaking change needs a new path, `/api/v2/`, published alongside v1; v1 is not changed in
  place.
- Clients should ignore fields they do not know.
- The API always serves the current dataset, so values change with data updates. Check
  `dataset.id` in responses. For a snapshot, use its original files in
  `downloads/<dataset_id>/`, which never change, or the files attached to its GitHub Release.

## Identifier and URL stability policy

The methodology page states this policy for users
([Identifiers and stable URLs](https://kiankyars.github.io/datacenter-atlas/methodology/#identifiers)):

- `site_id` is `vcc-site-` plus the first 20 hexadecimal characters of the SHA-256 of
  `physical_site_stable_key` (`_stable_id` in `datacenter_atlas/verified_construction_core.py`). It
  is stable as long as the curation key is.
- `project_id` is a version 5 UUID of the project's stable key, and `evidence_id` a version 5 UUID
  of the source kind, the source's identifier or curation key and its content hash (and, for some
  sources, its retrieval time): `stable_id` in `datacenter_atlas/repository.py`. A recapture with
  different content, or a capture filed under a new key, gets a new `evidence_id`.
- An identifier is never reused for a different entity. A merge or split retires every identifier
  that no longer describes the same entity, and a new entity gets a new identifier; `versions.json`
  lists the sites each version added or removed.
- `api/v1/` files and `sites/<site_id>/` pages exist only for records in the current version; a
  retired identifier returns 404 there, and its records remain in the original files of every
  `downloads/<id>/` that contained it.
- Version identifiers and `downloads/<id>/` directories are permanent. `*_stable_key` values are
  curation keys, not external identifiers.

Keep identifiers stable: never change a stable key just to rename a record. If a key must change,
record the reason and the old and new identifiers in the data update's definition.

## Updating the data

The atlas is an ongoing dataset. Add sites, refresh dated construction observations and correct
locations or other facts as evidence becomes available.

Divide research into bounded country passes. Each contributor searches local primary sources for
missing sites, checks existing records for newer construction statuses, and resolves known factual
corrections. Use the shared site, project and evidence record formats. Before combining parallel
passes, check all proposed names, campus aliases and identifiers against the full atlas and the
other country assignments. Publish supported changes through the routine update process below;
publication does not depend on reaching a site-count target or product-version milestone.

1. Gather a dated primary source for the claimed project status and a source for the location.
   Admissions may be announced, permitted, under construction, completed or operating; the
   observation must fall within 90 days of the update. Completion of a named work package must
   retain that scope and must not imply an operating campus. Check
   existing campus names and aliases before adding a site; add a project to the existing site when
   the work is another building or phase at the same campus.
2. Record source URLs, retrieval dates, licences and supported facts. Preserve the observation date
   and location precision. Check for subsequent opening, cancellation or other status changes.
3. Record the reviewed changes in `definitions/atlas-update-YYYY-MM-DD.json`, retaining stable
   site and project identifiers and pinning the previous dataset manifest. Build the dated
   snapshot with `python3 scripts/build_dataset_update.py --input definitions/atlas-update-YYYY-MM-DD.json`,
   then repeat with `--validate-only` and run `tests.test_dataset_update`. The builder keeps
   existing observation dates and recalculates their age at the update date. Historical batch
   reproduction is documented separately in [expansion_200.md](expansion_200.md). Existing
   published files remain unchanged so earlier analyses can be reproduced.
4. Ensure Git tracks every file listed in the new manifest, then point `current_dataset` in
   `site/config.json` at the directory. Add dictionary and vocabulary entries for any new fields
   or codes. Historical directory names are storage identifiers, not public product versions.
5. Build and refresh generated metadata:

   ```sh
   python3 scripts/build_public_site.py --output _site --force
   python3 site/e2e/check_public_metadata.py --site _site --write
   python3 site/e2e/check_public_metadata.py --site _site
   ```

   The metadata script updates `CITATION.cff` and marked blocks in `README.md` and `DATA_LICENSE.md`
   from the built API. Fix any stale hand-written figures or validation commands it reports. Public
   pages use tokens for counts and dates; describe the data by its update and observation dates.
6. Run the relevant tests and inspect the map, changed site pages and downloads. Commit and push
   to `main`; CI builds, deploys and checks the live site. `downloads/latest/` follows the new data,
   and existing archive paths remain available. Optional GitHub Releases archive data files; they
   do not define a separate public product lifecycle.

## Tests

```sh
python3 -m unittest -v tests.test_public_site   # offline; builds once into a temporary directory
node --test site/js-tests/*.test.mjs            # pure frontend logic, no browser (Node 22 or newer)
python3 -m pytest site/e2e/test_ci_scripts.py   # CI helpers: pages server, metadata check, live checks, release notes
```

The unit tests check, among other things, manifest validation, counts, typed conversion, that
every site has a page and a JSON document, SQLite keys, checksums, the zip, the Data Package, KML,
internal links, escaping, deterministic rebuilds, unknown tokens, dictionary coverage and the
Content-Security-Policy. CI runs the same module from the directory above the checkout, as
`python -m unittest -v datacenter_atlas.tests.test_public_site`.

The browser end-to-end tests in `site/e2e/test_site_e2e.py` use Playwright. They run in CI against
the build served by `pages_server.py`, block every non-local request (basemap tiles get a blank
image), read their expected counts from `api/v1/index.json` and save screenshots to
`site-screenshots/`. Besides the explorer, static pages and downloads, they check:

- that `llms.txt`, the OpenAPI description (every endpoint of `index.json` described, every path
  served, every `$ref` resolvable, required keys present) and the download landing pages work, and
  that the README, `CITATION.cff` and `DATA_LICENSE.md` match the build;
- accessibility with axe at 1440x900 in light and dark mode and on a 390x844 phone with the detail
  sheet open, failing on every critical violation and on serious `color-contrast`,
  `aria-dialog-name` and `scrollable-region-focusable` ones (other serious findings are reported as
  warnings);
- layout geometry: the first result row is above the fold at 1440x900, first table columns are at
  least 96px wide at 820px, "Fit to results" shows every marker at 360px, and Tab never leaves the
  phone detail sheet;
- animated map moves (a context without reduced motion), so auto-fit is tested with the code paths
  real visitors get;
- WebMCP without a supporting browser: the explorer works when `document.modelContext` is absent,
  throws or rejects, and with a recording stand-in it registers `search_datacenter_sites`,
  `get_datacenter_site` and `get_datacenter_dataset_info` (read-only, untrusted-content hints),
  whose calls drive the visible explorer, and aborts them on `pagehide`.

The pinned, hash-locked tooling (Playwright, pytest and axe-playwright-python) is listed in
[`site/e2e/requirements.txt`](../site/e2e/requirements.txt). Running the tests locally downloads a
browser:

```sh
python3 -m pip install --require-hashes --only-binary :all: -r site/e2e/requirements.txt
python3 -m playwright install chromium
python3 scripts/build_public_site.py --output _site --force
python3 -m pytest site/e2e -q
```

Without `ATLAS_BASE_URL`, the tests serve `_site/` (or `$ATLAS_SITE_DIR`) themselves with
`pages_server.py` under the `/datacenter-atlas/` sub-path on an ephemeral 127.0.0.1 port.
Environment variables:

| Variable | Meaning |
| --- | --- |
| `ATLAS_BASE_URL` | Test an already running server instead, for example `http://127.0.0.1:8000/datacenter-atlas/`; it must follow GitHub Pages' rules (use `pages_server.py`) |
| `ATLAS_SITE_DIR` | Built site to serve when `ATLAS_BASE_URL` is unset (default `_site/`) |
| `ATLAS_SCREENSHOT_DIR` | Where screenshots go (default `site-screenshots/`) |
| `ATLAS_E2E_REQUIRED` | `1` turns every skip (no Playwright, no built site) into an error; CI sets it |

Without Playwright the browser tests skip; the API, download, metadata and server checks still run
when a built site is available.

## CI and deployment

- [`.github/workflows/pages.yml`](../.github/workflows/pages.yml) (workflow "Public site") runs on
  pushes to `main`, on pull requests, weekly and on manual dispatch. Jobs:
  - `build` (permissions `contents: read`, `pages: read`): builds the site with the production base
    URL and `--source-commit "$GITHUB_SHA"`, runs `check_public_metadata.py`, the unit tests and
    the JavaScript tests (it fails if `site/js-tests/` has no `*.test.mjs` files), and then the
    Playwright tests against the build served by `pages_server.py`. It always uploads the
    `site-screenshots` artifact. On pushes to `main` it uploads `_site` as the Pages artifact
    before the browser tooling is installed, so nothing that tooling downloads can alter what is
    deployed.
  - `deploy` (permissions `pages: write`, `id-token: write`): only for pushes to `main`, after the
    whole `build` job has passed; publishes with `actions/deploy-pages` to the `github-pages`
    environment. Deployments share the `pages` concurrency group and do not cancel each other; a
    newer push to a pull request cancels that pull request's older run.
  - `verify-live` (`contents: read`): after each deploy,
    [`site/e2e/live_checks.py`](../site/e2e/live_checks.py) waits (up to 10 minutes) until the live
    `api/v1/index.json` reports the pushed commit, then checks that every API endpoint answers 200
    with JSON (or CSV) and `Access-Control-Allow-Origin: *`, that the main pages, `llms.txt`, the
    feeds and the sitemap answer 200, and that every file in `downloads/latest/SHA256SUMS` matches
    its checksum.
  - `release` (`contents: write`; opt-in): with the repository variable `ATLAS_GITHUB_RELEASES` set
    to `true`, after `verify-live`, creates the GitHub Release `data-<dataset id>` once per dataset
    version from the deployed files: the version's zip, `SHA256SUMS`, the three CSVs,
    `sites.geojson`, `atlas.sqlite`, `atlas.xlsx`, `atlas.json` and `datapackage.json`, with notes
    from [`site/e2e/release_notes.py`](../site/e2e/release_notes.py) (counts, added and removed
    sites, caveats, licence). Later pushes for the same version skip it. Releases give each version
    an immutable copy of its derived formats and a release event people can watch.
  - `monitor` (`contents: read`, `issues: write`): weekly (Mondays 05:23 UTC) and on manual
    dispatch with `job` set to `monitor`, re-runs the live checks and checks every evidence
    `source_url` politely (one request per second, 15-second timeout). URLs answering 404 or 410,
    or whose host no longer exists, are listed in a single open issue labelled `link-rot`, which is
    updated each week and closed when none remain; blocked or failing requests are listed as
    unverified. The report is also kept as the `link-report` artifact. Monitor runs have their own
    concurrency group, so they never displace a pending deploy.
- Every action is pinned to a full commit SHA with its release in a comment. To update one, resolve
  the new release's commit (`gh api repos/<owner>/<action>/git/ref/tags/<tag>`, following an
  annotated tag to its commit) and replace both. A Dependabot configuration for the
  `github-actions` ecosystem, if added, proposes these updates as pull requests.
- [`.github/workflows/clean-clone.yml`](../.github/workflows/clean-clone.yml) also builds the site
  into a temporary directory, runs `check_public_metadata.py`, `tests.test_public_site` and `ruff`
  on the builder. Its checkout does not persist the token.
- To roll back, revert the offending commit on `main`; the next push redeploys.

One-time repository and account settings:

| Setting | Where | Why |
| --- | --- | --- |
| Pages source: **GitHub Actions** | Settings, Pages, Build and deployment | The workflow deploys the site. |
| Require actions pinned to a full-length commit SHA; allow only GitHub-owned actions and `astral-sh/setup-uv` | Settings, Actions, General | Enforces the pinning above for future workflow edits. |
| `ATLAS_GITHUB_RELEASES` = `true` | Settings, Secrets and variables, Actions, Variables | Turns on the `release` job. |
| Zenodo GitHub integration for this repository | <https://zenodo.org/account/settings/github/> | Archives each GitHub Release and mints a version DOI under one concept DOI. Then add the concept DOI to the README (badge), to `CITATION.cff` (`doi`, through `doi` in `site/config.json`, which `check_public_metadata.py --write` reads) and to the site's metadata. Zenodo archives the repository snapshot at the release tag, which includes every version's original files. |
| `robots.txt` at the account's Pages root | the `kiankyars/kiankyars.github.io` repository | Crawlers read `robots.txt` only at the host root (RFC 9309), so the site's own `/datacenter-atlas/robots.txt` is informational and its `Sitemap:` line is never read there. Add `User-agent: *`, `Allow: /` and `Sitemap: https://kiankyars.github.io/datacenter-atlas/sitemap.xml` to the root `robots.txt`. |
| Google Search Console and Bing Webmaster Tools | URL-prefix property `https://kiankyars.github.io/datacenter-atlas/` | Verify the property (an HTML verification file committed to `site/static/` is copied to the site root), submit `sitemap.xml`, and watch the Dataset structured-data report. Bing can import the Search Console property. |

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Manifest or checksum mismatch | A tracked dataset file changed. Restore it from Git; never edit a manifest to match. |
| Unknown template token | Correct the token in `site/content/` or `site/templates/` using the list above. |
| Output directory is not empty | Choose a new directory, or pass `--force` to replace an earlier build. |
| A column has no dictionary description | Add it to `site/field_descriptions.json`. |
| "The public metadata disagrees with the build" | Run `check_public_metadata.py --write` and fix the listed prose in the data update workflow. |
| `site/static/... is missing` or an output path is written twice | Restore the asset the page layout needs (`assets/site.css`, `site.js`, `site-map.js`, `app.js`, the vendored Leaflet files, `favicon.svg`), or rename a static file that collides with a generated path such as `api/` or `downloads/`. |
| A browser test passes locally but the URL is 404 in production | Serve the build with `pages_server.py`, not `http.server`: GitHub Pages never lists directories. |
| The live site is not updated | Check that the `deploy` and `verify-live` jobs ran for the push to `main` and that Pages uses GitHub Actions as its source. |

## Consolidated project records

The 13 October consolidation is reproduced with `scripts/build_consolidated_dataset.py` and
`definitions/atlas-consolidation-2026-10-13.json`. See [repository_consolidation.md](repository_consolidation.md)
for identity mapping, complete source records and the additional project-detail fields. Published
dataset directories may have a descriptive suffix after the date when there are multiple
archives on one day. The manifest update date must still match the date prefix.
