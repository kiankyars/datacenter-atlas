# Data licence

Data Center Atlas combines material the project wrote with facts taken from third-party sources,
and the two are licensed differently. This file covers every dataset under
[`verified_construction_core/`](verified_construction_core/), the derived downloads and API
published at <https://kiankyars.github.io/datacenter-atlas/>, and the project's documentation.
Source code is licensed separately under the [MIT License](LICENSE).

| Material | Terms |
| --- | --- |
| Atlas-authored data and documentation | [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/) |
| Third-party facts, quoted titles, source URLs and geometries | The source's own terms, recorded on each evidence row and in each dataset's `ATTRIBUTION.txt` |
| Geometries derived from OpenStreetMap | © OpenStreetMap contributors, [Open Database License 1.0 (ODbL)](https://opendatacommons.org/licenses/odbl/1-0/) |
| Required source notices | Reproduced under [Required notices](#required-notices); keep them with the data |

## Atlas-authored data: CC BY 4.0

The following were created by Data Center Atlas and are licensed under CC BY 4.0:

- identifiers and stable keys (`site_id`, `project_id`, `evidence_id` and the `*_stable_key`
  columns);
- the structure of the tables, schemas and GeoJSON, and of the derived formats (SQLite, JSON,
  NDJSON, KML, Data Package and the JSON API);
- classifications assigned during review, such as physical-status codes and methods, geometry use
  scopes, authority and scope classes, verification postures and evidence roles;
- review annotations: unknown and not-estimated reasons, precision-scope text, site-distinctness
  decisions, imagery-review outcome labels, and the selection and release-gate reports;
- the structure of typed observations (metric, stage, interval, method, confidence and unit);
- documentation, including the README, the `docs/` directory and the website's text.

Attribute it as **Data Center Atlas (Kian Kyars), https://kiankyars.github.io/datacenter-atlas/**,
name the dated data snapshot you used, and say whether you changed the data. For example:

<!-- atlas:attribution-example -->
> Data: Data Center Atlas (Kian Kyars), https://kiankyars.github.io/datacenter-atlas/, data updated
> 2026-10-27, CC BY 4.0. Includes data © OpenStreetMap contributors (ODbL 1.0) and from the other
> sources listed in the dataset's ATTRIBUTION.txt.
<!-- /atlas:attribution-example -->

## Third-party material keeps its source terms

Every status, locator and typed value in the atlas cites an evidence row. The Atlas does not hold
the rights to those sources, and CC BY 4.0 does not extend to them.

- **Recorded per row.** Each row of `evidence.csv` carries the source's `license` and
  `attribution`, and each dataset's `ATTRIBUTION.txt` lists every source with its terms and rights
  links. A project's geometry is governed by the evidence row named in its `geometry_evidence_id`.
- **Facts and links, not copies.** The Atlas records compact factual extractions (dates,
  physical-status statements, names, addresses, coordinates, and parcel or boundary geometry)
  together with a link, the retrieval time and a content hash. It does not redistribute
  third-party documents, web pages, PDFs, imagery, map tiles or other media.
- **Most sources are not openly licensed.** Many rows, including most company web pages, are
  marked `all-rights-reserved` or assert no open licence. Their titles and URLs are cited so that
  each fact can be checked; they are not relicensed.
- **Some open terms add conditions.** A few sources are share-alike, or restrict commercial use or
  derivatives. Check a row's `license` before reusing the material it describes.

The basemaps shown on the website (OpenStreetMap and EOX satellite tiles, and CARTO's where they are
offered) are not part of the dataset and are not covered by its CC BY 4.0 licence. Your browser loads
them directly from their providers, under the providers' terms; the website's
[about page](https://kiankyars.github.io/datacenter-atlas/about/#legal) credits each one.

## OpenStreetMap-derived geometries: ODbL 1.0

Some locators are derived from OpenStreetMap; their geometry evidence row has `license` set to
`ODbL-1.0` (<!-- atlas:osm-geometry-count -->72 of the 833 project geometries, on 67 sites, in the 2026-10-27 data snapshot<!-- /atlas:osm-geometry-count -->). These
geometries are © OpenStreetMap contributors and are available under the ODbL 1.0, not CC BY 4.0.
Credit "© OpenStreetMap contributors" and link to <https://www.openstreetmap.org/copyright>. If you
publicly use a derivative database of these geometries, the ODbL's share-alike terms apply to that
database.

Other geometry providers publish under their own open licences and require attribution: for
example Kartverket, the National Land Survey of Finland and the ACT Government (CC BY 4.0), the
French DGFiP cadastre (Licence Ouverte 2.0) and the City and County of Denver (CC BY 3.0). Each
dataset's `ATTRIBUTION.txt` has the complete list.

## Required notices

The atlas uses one City of Chicago building record, as identity context for Digital Realty's
330 East Cermak project. The City's terms require the following notice, reproduced verbatim from
the [v0.17 preview README](verified_construction_core/2026-08-20-preview-v0.17/README.md):

City of Chicago data notice

Attribution: City of Chicago
Terms: https://www.chicago.gov/city/en/narr/foia/data_disclaimer.html

Required disclaimer:
“This site provides applications using data that has been modified for use from its original source, www.cityofchicago.org, the official website of the City of Chicago. The City of Chicago makes no claims as to the content, accuracy, timeliness, or completeness of any of the data provided at this site. The data provided at this site is subject to change at any time. It is understood that the data provided at this site is being used at one’s own risk.”

Additional terms reminder:
Comply with any additional Terms of Use set forth by the City agency or department providing data used by the software application, or other secondary or derivative application, including, without limitation, requirements to include additional citations or disclaimers at the site where the application can be accessed or downloaded.

Other source-specific notices, such as the e-Stat processed-boundary notice and the Open
Government Licence – Alberta statement, appear in each dataset's `ATTRIBUTION.txt` and on the
website's [attribution page](https://kiankyars.github.io/datacenter-atlas/about/attribution/).

## No warranty; not advice

The data is provided "as is", without warranty of any kind, express or implied, including as to
accuracy, completeness, timeliness or fitness for a particular purpose. It is compiled from public
sources that can be incomplete, out of date or wrong. It is not legal, surveying, investment,
engineering or operational advice.

Read the data on its own terms. A status is the last observed physical status as of the dataset's
lifecycle reference date, not the current status. A locator is not a building footprint or a
surveyed boundary unless its recorded semantics say so. A missing capacity, role or workload is
unknown, not zero. The dataset is not a census of data-centre construction.

## Questions and rights concerns

If you hold rights in material the atlas cites and believe it is used beyond its terms, or if
anything here is unclear, please open an issue at
<https://github.com/kiankyars/datacenter-atlas/issues>.
