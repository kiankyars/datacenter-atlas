# Data Center Atlas

Data Center Atlas is an open, evidence-backed dataset of data-centre construction worldwide.
Public information about where data centres are being built is scattered across company
disclosures, government records and filings, and is often vague about location and timing. The
atlas keeps only projects with a dated, authoritative report of physical construction work and a
reviewed locator whose precision is stated, and it links each status, locator and typed value to
its source, with retrieval times, content hashes and licences. Unknown values stay unknown, and
nothing is inferred to make a record look complete.

**Website: <https://kiankyars.github.io/datacenter-atlas/>** (map explorer, a page for every site,
downloads, API documentation and methodology).

## Current dataset

- **Version:** `2026-08-20-v0.18-draft-thirty-fifth-reviewed`, the thirty-fifth reviewed checkpoint
  of the v0.18 draft, dated **2026-09-25**.
- **Contents:** **197 physical sites** with **200 construction projects** in **46 countries**
  (131 sites outside the United States), backed by **897 evidence rows**.
- **Lifecycle cutoff:** **2026-08-20**. Every status was observed between 2026-05-22 and
  2026-08-20.
- **Release status:** a reviewed **draft**, not a final release (`publishable_as_final` is
  false). Six of the nine final-release gates are not yet met:

| Gate | Required | Current | Met |
| --- | --- | --- | --- |
| Physical sites | 200 | 197 | No |
| Sites added since the v0.17 preview | 100 | 97 | No |
| Countries | at least 40 | 46 | Yes |
| Sites outside the United States | at least 100 | 131 | Yes |
| Largest single-country share | at most 40% | 33.5% (United States) | Yes |
| Projects with an imagery-review outcome | 200 | 10 | No |
| Blind re-review of a fixed 20-project sample | 19 agreements | not started | No |
| Clean-clone rebuild | checked at release | not yet recorded | No |
| Publication authorised | explicit sign-off | never granted to drafts | No |

The figures come from the dataset's
[`selection-report.json`](verified_construction_core/2026-08-20-v0.18-draft-thirty-fifth-reviewed/selection-report.json).
The last preview, [v0.17](verified_construction_core/2026-08-20-preview-v0.17/README.md), has 100
sites; the reviewed drafts extend it towards 200. All 53 versions remain available.

## Get the data

No key or sign-up is needed. GitHub Pages serves the files with permissive CORS, so scripts and
browser tools can read them directly.

| File | Contents |
| --- | --- |
| [`sites.csv`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/sites.csv) | One row per physical site: name, country, display coordinates, geometry, statuses and status dates |
| [`projects.csv`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/projects.csv) | One row per project: status, status date and method, locator semantics, typed power observations, unknown reasons |
| [`evidence.csv`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/evidence.csv) | One row per source: URL, publisher, kind, roles, dates, licence, attribution and content hash |
| [`sites.geojson`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/sites.geojson) | Site geometries (Point, Polygon, MultiPolygon) with site attributes |
| [`atlas.sqlite`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/atlas.sqlite) | The three tables with keys, link tables and a `site_overview` view |
| [`atlas.json`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/atlas.json) | Every record as typed JSON: empty values become `null` and JSON columns are parsed |
| [`sites.kml`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/sites.kml) | Placemarks for Google Earth and GIS tools |
| [`datapackage.json`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/datapackage.json) | Frictionless Data Package descriptor: field types, keys, sizes and hashes |
| [`SHA256SUMS`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/SHA256SUMS) | SHA-256 checksum of every file in the directory |
| [`datacenter-atlas-latest.zip`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/datacenter-atlas-latest.zip) | Every file in the directory except `SHA256SUMS`, including NDJSON, `schema.json`, `selection-report.json`, `ATTRIBUTION.txt` and the manifest |

In the CSVs an empty cell means unknown or not applicable, and columns ending in `_json` hold JSON
text. The [data dictionary](https://kiankyars.github.io/datacenter-atlas/data/dictionary/)
describes every column.

`downloads/latest/` follows the current version. For reproducible work, use the pinned directory,
which never changes:
<https://kiankyars.github.io/datacenter-atlas/downloads/2026-08-20-v0.18-draft-thirty-fifth-reviewed/>
(its zip is named `datacenter-atlas-2026-08-20-v0.18-draft-thirty-fifth-reviewed.zip`). Every
earlier version has its own directory with its original files; see
[versions](https://kiankyars.github.io/datacenter-atlas/versions/).

### API

Static JSON over HTTPS, versioned under `https://kiankyars.github.io/datacenter-atlas/api/v1/`.
Changes within `v1` are additive only. Reference:
<https://kiankyars.github.io/datacenter-atlas/api/>.

| Endpoint | Returns |
| --- | --- |
| [`index.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/index.json) | Dataset metadata, endpoint templates, and downloads with hashes |
| [`sites.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/sites.json), [`sites.geojson`](https://kiankyars.github.io/datacenter-atlas/api/v1/sites.geojson) | Every site summary, as an array or as a FeatureCollection |
| `sites/{site_id}.json` | One site with all its projects and evidence |
| [`projects.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/projects.json), `projects/{project_id}.json` | Project records |
| [`evidence.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/evidence.json), `evidence/{evidence_id}.json` | Evidence records |
| [`countries.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/countries.json), `countries/{ISO2}.json` | Country summaries and their sites |
| [`stats.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/stats.json) | Aggregate counts by status, country, month, geometry and more |
| [`versions.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/versions.json) | Every dataset version, with hashes and the sites each one added or removed |
| [`vocabularies.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/vocabularies.json) | Labels and descriptions for coded values |

### Examples

Shell (curl and jq):

```sh
BASE=https://kiankyars.github.io/datacenter-atlas

# Download a file and verify it against the published checksums
curl -fsSLO "$BASE/downloads/latest/sites.csv"
curl -fsSLO "$BASE/downloads/latest/SHA256SUMS"
sha256sum --check --ignore-missing SHA256SUMS  # macOS: shasum -a 256 --check --ignore-missing SHA256SUMS

# One site with its projects (CDC Eastern Creek has two)
curl -fsSL "$BASE/api/v1/sites/vcc-site-3c1f872aa59b74b065ea.json" \
  | jq '.projects[] | {name, last_observed_physical_status, status_as_of}'
```

Python, standard library only:

```python
import csv, io, json, urllib.request

URL = "https://kiankyars.github.io/datacenter-atlas/downloads/latest/projects.csv"
with urllib.request.urlopen(URL) as response:
    projects = list(csv.DictReader(io.TextIOWrapper(response, encoding="utf-8")))

for project in projects[:5]:
    power = json.loads(project["power_observations_json"])  # [] means no typed observation
    print(project["name"], project["last_observed_physical_status"], project["status_as_of"],
          [(o["metric"], o["stage"], o["base"], o["unit"]) for o in power])
```

pandas:

```python
import pandas as pd

URL = "https://kiankyars.github.io/datacenter-atlas/downloads/latest/sites.csv"
# Treat only empty cells as missing: "NA" is a valid ISO country code (Namibia).
sites = pd.read_csv(URL, keep_default_na=False, na_values=[""])
print(sites["country"].value_counts().head(10))
```

DuckDB (reads HTTPS URLs through its `httpfs` extension, which loads automatically):

```sql
SELECT last_observed_physical_status AS status, count(*) AS projects
FROM read_csv_auto('https://kiankyars.github.io/datacenter-atlas/downloads/latest/projects.csv')
GROUP BY status
ORDER BY projects DESC;
```

R (readr and sf):

```r
library(readr)
library(sf)

base <- "https://kiankyars.github.io/datacenter-atlas/downloads/latest/"
projects <- read_csv(paste0(base, "projects.csv"), na = "")  # "NA" is Namibia's ISO code
sites <- st_read(paste0(base, "sites.geojson"))
table(projects$last_observed_physical_status)
```

SQLite:

```sh
curl -fsSLO https://kiankyars.github.io/datacenter-atlas/downloads/latest/atlas.sqlite
sqlite3 atlas.sqlite "SELECT name, country, newest_status_as_of FROM site_overview ORDER BY newest_status_as_of DESC LIMIT 10;"
```

To explore the SQLite file in a browser, open it in
[Datasette Lite](https://lite.datasette.io/?url=https://kiankyars.github.io/datacenter-atlas/downloads/latest/atlas.sqlite).
The [data page](https://kiankyars.github.io/datacenter-atlas/data/) has more recipes, including
geopandas, JavaScript, QGIS and Google Earth.

## How a site qualifies

A project is included only when all of these hold. The full contract is in the
[methodology](https://kiankyars.github.io/datacenter-atlas/methodology/) and in
[docs/verified_construction_core.md](docs/verified_construction_core.md).

1. **Recent physical work.** An authoritative source, such as a company disclosure, government
   record or regulatory filing, reports physical construction on the named project as of a date in
   the 90 days ending on the fixed lifecycle cutoff (2026-05-22 to 2026-08-20). Site preparation,
   civil works, foundations, shell, MEP/electrical work, general construction, commissioning and
   expansion works count. Announcements, land deals, permits, grid requests and planned opening
   dates do not, and a later page edit or retrieval does not refresh the date.
2. **One distinct physical site.** The project is linked to one reviewed campus. Further buildings
   or phases on a campus already in the atlas do not add a site.
3. **A reviewed locator.** An official boundary or a source-specific point or polygon, such as an
   official parcel or address point, a coordinate published by the developer or an authority, or a
   named map feature, with its scope and precision recorded. Locality centroids, head offices and
   unrelated nearby buildings are rejected.
4. **Closed evidence.** The status, the locator and every typed value cite an evidence row with its
   URL, publisher, retrieval time, content hash, licence and attribution.

## Limitations

Read these before using the data.

- **Not a census.** The atlas is a reviewed sample held to a strict evidence bar, not a complete
  list; a site's absence says nothing about whether it is being built. Coverage follows what
  sources publish: the United States, Australia and Germany hold 98 of the 197 sites.
- **Last observed physical status, not current status.** Each status is the latest qualifying
  observation on or before 2026-08-20. Projects may since have finished, paused or been cancelled.
- **Locators are not footprints.** 145 sites are located by a point and 52 by a polygon or
  multipolygon, and only 5 projects use an official site boundary. A polygon may outline a parcel,
  a campus, a host estate or an existing building used only as a locator, rather than the works.
  Numeric positional uncertainty is known for 10 projects; elsewhere the record says why it is
  unknown.
- **Capacity is unknown unless a typed observation exists.** 22 of the 200 projects carry one (24
  observations, mostly planned critical IT load). Critical IT load, grid connection and gross
  facility power are different measures and must not be added together. A missing value means
  unknown, never zero. There are no annual-energy observations and one PUE value.
- **Roles and workloads are sparse.** The data has 11 role claims (9 operators and 2 customers)
  and 8 workload observations, all scoped as intended rather than current or operational. No owner,
  tenant or user is recorded, operating model is known for 4 projects, and development type for
  none.
- **No independent imagery verification.** `independent_imagery_verification` is false for every
  project. Ten projects carry an imagery-review outcome; none of them creates a construction claim.
- **No benchmark parity.** No licensed row-level benchmark is available, so the atlas claims no
  completeness or accuracy parity with commercial trackers such as SemiAnalysis.
- **Not advice.** The data is provided as is and is not legal, surveying, investment, engineering
  or operational advice.

## Cite

Cite the version you used. GitHub's "Cite this repository" button reads [CITATION.cff](CITATION.cff).

> Kyars, K. (2026). *Data Center Atlas: Verified Construction Core* (Version
> 2026-08-20-v0.18-draft-thirty-fifth-reviewed) [Data set].
> https://kiankyars.github.io/datacenter-atlas/

```bibtex
@misc{kyars2026datacenteratlas,
  author = "Kyars, Kian",
  title  = "Data Center Atlas: Verified Construction Core",
  year   = "2026",
  note   = "Dataset version 2026-08-20-v0.18-draft-thirty-fifth-reviewed, checkpoint 2026-09-25",
  url    = "https://kiankyars.github.io/datacenter-atlas/"
}
```

## Licence

- **Atlas-authored data and documentation** (identifiers, structure, classifications, review
  annotations, docs): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Attribute
  "Data Center Atlas (Kian Kyars), https://kiankyars.github.io/datacenter-atlas/".
- **Third-party facts, titles, URLs and geometries** keep their sources' terms, recorded per row in
  `evidence.csv` (`license`, `attribution`) and in each dataset's `ATTRIBUTION.txt`. Many sources
  are all-rights-reserved; the atlas records compact facts and links, not documents or imagery.
- **OpenStreetMap-derived geometries:** © OpenStreetMap contributors,
  [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
- **Code:** [MIT](LICENSE). The vendored Leaflet 1.9.4 keeps its
  [BSD 2-Clause licence](site/static/assets/vendor/leaflet/LICENSE).

[DATA_LICENSE.md](DATA_LICENSE.md) has the full terms and the City of Chicago notice that must
accompany the data.

## Contribute or report a correction

- **Correction:** use the
  [correction form](https://github.com/kiankyars/datacenter-atlas/issues/new?template=correction.yml).
  Every site page has a "Report a correction" link that fills in the site ID.
- **New site:** use the
  [new-site form](https://github.com/kiankyars/datacenter-atlas/issues/new?template=new-site.yml),
  with dated evidence of physical work and a precise locator.
- **Code and docs:** see [CONTRIBUTING.md](CONTRIBUTING.md).

Published versions are frozen. Accepted corrections are applied, and documented, in a later
checkpoint.

## Repository layout

| Path | Contents |
| --- | --- |
| [`verified_construction_core/`](verified_construction_core/) | Every dataset version (17 previews, 36 drafts): CSVs, GeoJSON, schema, selection report, attribution and manifest. Frozen; never rewritten. |
| [`definitions/`](definitions/) | Hash-pinned contracts for each reviewed batch |
| [`sources/`](sources/) | Compact, attributed source facts and research packets used as build inputs |
| [`datacenter_atlas/`](datacenter_atlas/) | Standard-library Python package: dataset builders and validators, and `public_site.py`, the website builder |
| [`scripts/`](scripts/) | Command-line entry points, including `build_expansion_200_draft.py` and `build_public_site.py` |
| [`site/`](site/) | Website sources: `config.json` (which dataset is current), page content, templates, static assets, vocabularies, field descriptions and browser tests |
| [`tests/`](tests/) | `unittest` suites |
| [`docs/`](docs/) | Methodology, selection contract, expansion log and maintainer notes ([public_site.md](docs/public_site.md)) |
| [`.github/`](.github/) | CI workflows (clean-clone checks, website build and deploy) and issue forms |

The remaining top-level directories, and the small Python wrappers at the root, belong to the
wider research workspace that preceded the core. Git keeps their code and provenance manifests but
not their large payloads; see [Project history](#project-history).

## Rebuild and test

Requirements: Python 3.11 or newer. A clean clone contains every input; after cloning, everything
below uses only the standard library and works offline.

```sh
git clone https://github.com/kiankyars/datacenter-atlas.git
cd datacenter-atlas

# Re-derive the current dataset from its hash-pinned inputs and compare every byte
python3 scripts/build_expansion_200_draft.py --batch thirty-fifth-reviewed --validate-only

# Build the website, API and downloads into _site/ (add --force to rebuild over an earlier build),
# then preview it at http://localhost:8000/
python3 scripts/build_public_site.py --output _site
python3 -m http.server -d _site 8000

# Tests for the site builder and the current checkpoint
python3 -m unittest -v tests.test_public_site tests.test_expansion_200_thirty_fifth_reviewed
```

[docs/public_site.md](docs/public_site.md) covers the build options, the output layout, the API
versioning policy, how a new checkpoint becomes current and how CI deploys the site.

## Project history

The atlas grew out of a wider research workspace: source releases, OpenStreetMap and satellite
review lanes, and permit and registry assessments. Its September 2026 status snapshot, previously
this README, is in [docs/workspace_status_2026-09.md](docs/workspace_status_2026-09.md). The
expansion from 100 to 200 sites is logged checkpoint by checkpoint in
[docs/expansion_200.md](docs/expansion_200.md).
