# Prince William County Build-Out GIS

The Prince William County Planning Office publishes unusually useful data-center building,
campus/project, and planning-site layers. The Atlas assessment is nevertheless metadata-only.
Official county surfaces support interactive use, attribute export, and download, but the exact
layer rights do not establish the commercial redistribution rights needed for a public compiled
database.

The immutable assessment is
`source_assessments/pwc-build-out-2026-07-18-v1/`. It retains exact official retrieval metadata,
three count-only results, and derived layer schemas and coded-value domains. It contains no feature
rows or row-level addresses, coordinates, or feature geometries; aggregate layer extents remain
source metadata. The retrieval timestamp is
`2026-07-18T22:33:40Z`.

## Rights decision

The [Build-Out Analysis page](https://www.pwcva.gov/department/planning-office/build-out-analysis)
says that users can filter and export attribute tables and that all analysis layers are available
for download from the county GIS Open Data Portal. Availability to download is not, by itself, an
affirmative grant to redistribute the records in a commercial compiled-data product.

The official [PWC GIS Data Portal Terms of Use](https://gisdata-pwcgov.opendata.arcgis.com/pages/terms-of-use)
say the data is for reference purposes, impose disclaimers and indemnity, reserve the county's
right to deny access, and provide data as-is. They do not expressly grant commercial reuse,
redistribution, derivative-database publication, sublicensing, or downstream end-user access.
The county's [GTS Disclaimer](https://www.pwcva.gov/disclaimer/) likewise limits use as a legal or
design reference and disclaims accuracy and damages.

The ArcGIS item for the Open Data Portal web application has `licenseInfo: CC-BY-SA`, without a
version or deed URL. That license string is attached to the portal's **Web Mapping Application**
item; its scope over the layer datasets is not established. The separate layer 9 and 10 portal
items instead link to the county disclaimer, while layer 11's official `iteminfo` has blank
`licenseInfo`. The assessment therefore does not treat the portal-site item license as a license
for layers 9–11.

This is a provenance and product-governance decision, not legal advice. The lane is
`rights_blocked_metadata_only`: zero feature rows, zero facility leads, no source-derived public
release, and no unique-site count.

## Count snapshot and entity levels

At the pinned retrieval timestamp, official `returnCountOnly=true` queries returned:

- layer 9, **Data Center Buildings**: 243 building records;
- layer 10, **Data Center Campuses** / item title **Data Center Projects**: 72 campus/project
  records; and
- layer 11, **Data Center Sites**: 61 planning-site/application records.

These are three different entity levels. They must not be summed, treated as a deduplicated list,
or reported as 376 unique sites. The layer service publishes no relationships connecting the
levels, and a `GlobalID` field does not establish a documented cross-layer join. No automatic
merges are allowed.

The service describes Prince William County only, with exclusions and qualifications described on
the Build-Out page. This is neither global coverage nor proof that every county data-center record
is current or complete.

## Schema and evidence boundaries

The assessment pins all source fields, aliases, ArcGIS types, nullability/editability metadata,
coded-value domains, source coordinate reference metadata, layer extents, supported query formats,
and pagination capability. No feature query with `outFields=*`, geometry, or `outSR=4326` was made
because source-row redistribution rights are unresolved.

Gross floor area is kept in the source's square-foot unit. Building fields remain separate:
planned `GFA` with `GFASource`, building-permit `BPGFA`, `ApprovedGFA`, `PermittedGFA`, and
`REATaxedGFA`. Campus/project `RemainingGFA` and `PlannedGFA`, and planning-site/application `GFA`,
also remain source-scoped. Values from these fields were not retrieved. GFA must not be converted
to power capacity or annual energy.

The building `BuildingStatus` coded domain contains `Completed`, `Pending`, `Planned`,
`Under Construction`, and `Approved Site Plan`. If licensed rows are retrieved later, county value
`Under Construction` can be retained as county-sourced lifecycle evidence for that exact record
and retrieval snapshot. It is not an automatic merge or evergreen Atlas status. `Completed` is not
automatically operational; `PermitStatus`, campus `ProjectStatus`, and site/application `Status`
must not be promoted to physical-facility lifecycle without separate evidence.

The layers document no MW, MVA, power, energy, PUE, or workload fields. No such values are inferred.

## Licensed-access unlock path

Before a source-row release is built, obtain written county clarification or permission that
expressly covers layers 9–11 and:

- identifies whether a specific CC BY-SA version applies and its exact layer scope;
- permits commercial use, local storage, raw-response caching, modification, derivative-database
  creation, public display, and redistribution;
- addresses sublicensing or downstream user access, attribution and notices, and any share-alike
  obligation; and
- states refresh, retention, termination, and deletion requirements.

After those rights are documented, create a new assessment ID and retrieve each layer independently
through the official query endpoint with `where=1=1`, `outFields=*`, `returnGeometry=true`, and
`outSR=4326`. Use deterministic `OBJECTID` ordering and bounded pagination, verify the initial and
final count, reject duplicates or missing pages, retain and hash every raw response, preserve all
source fields, and do not auto-merge across entity levels.

## Build and offline validation

The network builder only requests official pages, service/layer definitions, item metadata, and
three count-only query responses. It refuses an existing output directory and contains no full-row
query URL:

```sh
python3 scripts/build_pwc_build_out_assessment.py \
  --output source_assessments/pwc-build-out-2026-07-18-v1
```

The frozen bundle validator performs zero network requests and verifies canonical JSON, exact file
sets, layer identities, field/domain contracts, counts and semantics, source retrieval hashes, and
manifest hashes:

```sh
python3 scripts/validate_pwc_build_out_assessment.py
```

The assessment SHA-256 is
`b279705f514b6e7b5d470c053f7261c6e605e3693e2299982914af2199da4e47`, the schema
SHA-256 is `e911c751ca28667ceb3dcb67afab85a6bb9c2e08f09803ffa6727660bb49710b`,
and the manifest SHA-256 is
`fbf0d777b1d01a245a8064e226427b74b691088e15e4cfa4f5a2e93d7d2ca397`.
