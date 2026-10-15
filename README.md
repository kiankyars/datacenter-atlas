# Data Center Atlas

Data Center Atlas maps data centres worldwide, from announced projects to operating facilities.
Search by location or company, filter by status, and open a site to see its projects and sources.

[**Open the atlas**](https://kiankyars.github.io/datacenter-atlas/) ·
[Browse sites](https://kiankyars.github.io/datacenter-atlas/sites/) ·
[Download data](https://kiankyars.github.io/datacenter-atlas/data/) ·
[API](https://kiankyars.github.io/datacenter-atlas/api/)

## Coverage

<!-- atlas:current-dataset -->
- **Coverage:** **435 physical sites**, **461 projects** and **53 countries**.
- **Data updated:** 2026-10-15.
- **Status observations:** 2023-12-01 to 2026-10-15. Each record includes its source and observation
  date.
<!-- /atlas:current-dataset -->

## Get the data

No key or sign-up is needed. GitHub Pages serves the files with permissive CORS, so scripts and
browser tools can read them directly.

| File | Contents |
| --- | --- |
| [`sites.csv`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/sites.csv) | One row per physical site: name, country, display coordinates, geometry, statuses and status dates |
| [`projects.csv`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/projects.csv) | One row per project: status, status date and method, locator semantics, typed power observations, unknown reasons |
| [`evidence.csv`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/evidence.csv) | One row per evidence item, that is a source as used for specific projects and roles (the same URL can appear in several rows): URL, publisher, kind, roles, dates, licence, attribution and content hash |
| [`sites.geojson`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/sites.geojson) | Site geometries (Point, Polygon, MultiPolygon) with site attributes |
| [`atlas.sqlite`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/atlas.sqlite) | The three tables with keys, link and observation tables, and a `site_overview` view |
| [`atlas.xlsx`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/atlas.xlsx) | Excel workbook: a README sheet plus the sites, projects and evidence tables (geometry omitted) |
| [`atlas.json`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/atlas.json) | Every record as typed JSON: empty values become `null` and JSON columns are parsed |
| [`sites.kml`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/sites.kml) | Placemarks for Google Earth and GIS tools |
| [`datapackage.json`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/datapackage.json) | Frictionless Data Package descriptor: field types, keys, sizes and hashes |
| [`SHA256SUMS`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/SHA256SUMS) | SHA-256 checksum of every data file in the directory |
| [`datacenter-atlas-latest.zip`](https://kiankyars.github.io/datacenter-atlas/downloads/latest/datacenter-atlas-latest.zip) | Every data file in the directory except `SHA256SUMS`, including NDJSON, `schema.json`, `selection-report.json`, `ATTRIBUTION.txt` and the manifest |

In the CSVs an empty cell means unknown or not applicable, and columns ending in `_json` hold JSON
text. The [data dictionary](https://kiankyars.github.io/datacenter-atlas/data/dictionary/)
describes every column, and the [download page](https://kiankyars.github.io/datacenter-atlas/downloads/latest/)
lists every file with its size and checksum. Language models and agents can start from
[`llms.txt`](https://kiankyars.github.io/datacenter-atlas/llms.txt).

<!-- atlas:version-files -->
`downloads/latest/` contains the current data. For reproducible work, use the
[archived files](https://kiankyars.github.io/datacenter-atlas/downloads/2026-10-15-research-twentyseventh/)
and verify them against their
[`SHA256SUMS`](https://github.com/kiankyars/datacenter-atlas/releases/download/data-2026-10-15-research-twentyseventh/SHA256SUMS).
<!-- /atlas:version-files -->

Archived CSVs, GeoJSON and source records remain unchanged. Generated formats such as SQLite,
Excel and ZIP may change when the builder changes; verify them against the current `SHA256SUMS`.
Earlier data is available in the [data archive](https://kiankyars.github.io/datacenter-atlas/versions/).

### API

Static JSON over HTTPS, versioned under `https://kiankyars.github.io/datacenter-atlas/api/v1/`.
Changes within `v1` are additive only. Reference:
<https://kiankyars.github.io/datacenter-atlas/api/>. The machine-readable contract is an
[OpenAPI 3.1 description](https://kiankyars.github.io/datacenter-atlas/api/v1/openapi.json) with a
[JSON Schema](https://kiankyars.github.io/datacenter-atlas/api/v1/schemas/index.json) for every
response.

| Endpoint | Returns |
| --- | --- |
| [`index.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/index.json) | Dataset metadata, endpoint templates, and downloads with hashes |
| [`sites.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/sites.json), [`sites.geojson`](https://kiankyars.github.io/datacenter-atlas/api/v1/sites.geojson) | Every site summary, as an array or as a FeatureCollection |
| `sites/{site_id}.json`, `sites/{site_id}.geojson` | One site with all its projects and evidence, or as a GeoJSON feature |
| [`projects.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/projects.json), `projects/{project_id}.json` | Project records |
| [`evidence.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/evidence.json), `evidence/{evidence_id}.json` | Evidence records |
| [`countries.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/countries.json), `countries/{ISO2}.json`, `.geojson`, `.csv` | Country summaries, and each country's sites as JSON, GeoJSON or CSV |
| [`stats.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/stats.json) | Aggregate counts by status, country, month, geometry and more, each with its unit |
| [`versions.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/versions.json) | Archived datasets, with their files, hashes and changes |
| [`vocabularies.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/vocabularies.json) | Labels and descriptions for coded values |
| [`citation.json`](https://kiankyars.github.io/datacenter-atlas/api/v1/citation.json) | The citation as APA, BibTeX, biblatex, RIS and CSL-JSON |

The map explorer keeps its view in the URL, so links reproduce a filtered view, for example
<https://kiankyars.github.io/datacenter-atlas/?country=AU&status=mep_electrical,shell>. The
parameters (`q`, `country`, `status`, `locator`, `power`, `from`, `to`, `sort` and `#site=`) and the
columns of its CSV and GeoJSON exports are documented in
[docs/public_site.md](docs/public_site.md#explorer-links-and-exports).

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

The consolidated records preserve investment, hardware, capacity, organizations and timelines in
`project_details_json`, with linked sources and original units, dates, qualifiers and scope. Excel
also provides separate metrics, parties, milestones and power-supply sheets.
[All projects and multi-site programs](https://kiankyars.github.io/datacenter-atlas/projects/) are browsable.
The [consolidation notes](docs/repository_consolidation.md) explain project matches and retained identities.

## How a site qualifies

1. A dated company disclosure, government record or regulatory filing identifies the project and
   supports its status: announced, permitted, under construction, completed or operational.
   A permit's scope is recorded; approval of one part does not mean the whole project is approved.
2. The project has a sourced location with its precision recorded and is checked against existing
   sites. A new building or phase at a known campus adds a project, rather than another site.
3. Each status, location and other fact links to its supporting source. Missing values stay unknown.

Sites stay in the Atlas as they open, pause, close or change status. An opening target does not
establish completion or operation; those changes need evidence. Unsupported or misidentified
records can still be corrected or removed.

The [methodology](https://kiankyars.github.io/datacenter-atlas/methodology/) explains selection,
project statuses, location precision and source handling.

## Reading the data

- Check each status date: it describes what the source reported, and the project may have changed.
  Dataset updates preserve earlier evidence dates unless newer evidence supports a change.
- Locations can represent a project, campus or surrounding estate. A marker is not a surveyed boundary.
- Capacity values distinguish IT load, facility power, grid connection and generation, with their scope
  and stage recorded. Do not add these measures together. A missing value is not zero.
- Coverage depends on public sources and varies across countries and languages.

## Cite

Include the data date in citations. GitHub's "Cite this repository" button reads [CITATION.cff](CITATION.cff),
and the site offers the same citation as
[BibTeX](https://kiankyars.github.io/datacenter-atlas/api/v1/citation.bib),
[RIS](https://kiankyars.github.io/datacenter-atlas/api/v1/citation.ris) and
[CSL-JSON](https://kiankyars.github.io/datacenter-atlas/api/v1/citation.json).

<!-- atlas:citation -->
> Kyars, K. (2026). *Data Center Atlas* (2026-10-15) [Data set].
> https://kiankyars.github.io/datacenter-atlas/downloads/2026-10-15-research-twentyseventh/

```bibtex
@misc{kyars2026datacenteratlas,
  author = "Kyars, Kian",
  title  = "Data Center Atlas",
  year   = "2026",
  note   = "Data as published 2026-10-15",
  url    = "https://kiankyars.github.io/datacenter-atlas/downloads/2026-10-15-research-twentyseventh/"
}
```
<!-- /atlas:citation -->

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
  with a dated primary source for its status and a precise locator.
- **Code and docs:** see [CONTRIBUTING.md](CONTRIBUTING.md).

Ongoing work is to add sites, update their statuses and improve existing records. Accepted
changes appear in the next data update, while earlier files remain available in the archive.
Maintainers can follow the [data update workflow](docs/public_site.md#updating-the-data).

Research in this order: **United States → China → United Kingdom → Germany → Japan**. Give each
contributor a bounded country pass to find missing sites, review later statuses and resolve known
corrections using local primary sources. Use the same record format and check names and campus
aliases against the full atlas so parallel assignments do not add duplicates. The
[country research notes](docs/country_research.md) track the candidate queue. Publish supported
additions and updates as they are ready.

## Repository layout

| Path | Contents |
| --- | --- |
| [`verified_construction_core/`](verified_construction_core/) | Current and archived data: CSVs, GeoJSON, schema, source attribution and file manifests. |
| [`definitions/`](definitions/) | Hash-pinned contracts for each reviewed batch |
| [`sources/`](sources/) | Compact, attributed source facts and research packets used as build inputs |
| [`datacenter_atlas/`](datacenter_atlas/) | Standard-library Python package: dataset builders and validators, and `public_site.py`, the website builder |
| [`scripts/`](scripts/) | Command-line entry points, including `build_expansion_200_draft.py` and `build_public_site.py` |
| [`site/`](site/) | Website sources: `config.json` (which dataset is current), page content, templates, static assets, vocabularies and field descriptions; `site/e2e/` holds the browser tests and the CI helpers (GitHub Pages-like server, metadata check, live checks, release notes) |
| [`tests/`](tests/) | `unittest` suites |
| [`docs/`](docs/) | Methodology, selection contract, expansion log and maintainer notes ([public_site.md](docs/public_site.md)) |
| [`.github/`](.github/) | CI workflows (clean-clone checks; website build, deploy, live checks, releases and weekly link monitor) and issue forms |

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
python3 scripts/build_consolidated_dataset.py --input definitions/atlas-consolidation-2026-10-13.json --validate-only

# Build the website, API and downloads into _site/ (add --force to rebuild over an earlier build),
# check this README, CITATION.cff and DATA_LICENSE.md against it, then preview it the way GitHub
# Pages serves it, at http://127.0.0.1:8000/datacenter-atlas/
python3 scripts/build_public_site.py --output _site
python3 site/e2e/check_public_metadata.py --site _site
python3 site/e2e/pages_server.py --directory _site --port 8000

# Tests for the site builder and current dataset
python3 -m unittest -v tests.test_public_site tests.test_expansion_200_thirty_sixth_reviewed
```

[docs/public_site.md](docs/public_site.md) covers the build options, the output layout, the API
compatibility policy, how to update the data and how CI deploys the site.

## Project history

The atlas grew out of a wider research workspace: source releases, OpenStreetMap and satellite
review lanes, and permit and registry assessments. Its September 2026 status snapshot, previously
this README, is in [docs/workspace_status_2026-09.md](docs/workspace_status_2026-09.md). The
earlier expansion work is documented in
[docs/expansion_200.md](docs/expansion_200.md).
