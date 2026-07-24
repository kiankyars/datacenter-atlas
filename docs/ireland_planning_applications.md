# Ireland planning-application data-centre observations

This lane publishes an open, dated set of Irish planning-application
observations. It is not a facility inventory and does not claim to identify
every data centre in Ireland.

The source is the Department of Housing, Local Government and Heritage's
[IrishPlanningApplications dataset](https://data.gov.ie/en_GB/dataset/irishplanningapplications1)
and its official [ArcGIS FeatureServer](https://services.arcgis.com/NzlPQPKn5QF9v2US/arcgis/rest/services/IrishPlanningApplications/FeatureServer).
The data.gov.ie record identifies the dataset as Creative Commons Attribution
4.0, updated 2026-02-24, and describes merged participating Irish
local-authority registers with applications advertised as received since 2012.

The frozen release is
`source_assessments/ireland-planning-data-centres-2026-07-18-v1/`, retrieved at
`2026-07-18T23:00:48Z`. The bundle includes attribution and an indication of
the filtering, coordinate, date-normalization, and relationship-review changes
made by Data Center Atlas. The retained dataset and service artifacts are CC BY
4.0. Dataset-page and license-text copies are labeled separately as rights
evidence rather than being silently put under the dataset license.

## Bounded recall and precision audit

The official layer contained 499,712 rows at retrieval. The baseline filter was
the exact union of four description phrases: `data center`, `data centre`,
`datacenter`, and `datacentre`. It returned 102 rows.

Two additional high-precision phrases were assessed, and two broader variants
were measured but excluded:

| Incremental phrase outside the baseline | Rows | Decision |
| --- | ---: | --- |
| `data hall` | 11 | Included after description review |
| `data processing centre` | 1 | Included after description review |
| `co-location facility` | 2 | Excluded; both rows describe telecom towers, antennas, or broadband compounds |
| `server room` | 14 | Excluded; phrase is not specific enough for automatic inclusion |

The final filter therefore returned 114 observations. The two co-location
candidate descriptions are retained in a bounded, geometry-free review page so
the exclusion is reproducible. The final matched page was fetched once with
`outFields=*`, geometry in EPSG:4326, `OBJECTID ASC`, offset 0, and a 2,000-row
bound. All 114 rows had geometry and distinct OBJECTIDs.

This vocabulary is a high-precision planning-register lane, not a comprehensive
recall method. A relevant application can omit every chosen phrase, and the
source only covers participating authorities.

## Evidence and entity boundaries

Each output row remains a `planning_application_observation`. All 37 source
attributes, exact source strings, raw ArcGIS epoch dates, normalized UTC dates,
and source geometry are preserved. Whitespace and spelling variants in status,
decision, appeal, and authority fields are not silently consolidated.

Application status, decision, grant, expiry, withdrawal, further-information,
and appeal fields describe the planning process. They do not establish that a
facility was built, is under construction, or is operating. The release sets
construction evidence and operation evidence to false and leaves facility
lifecycle status null for every row.

The 114 rows include amendments, retention cases, extensions, further-
information activity, appeals, and repeated application identifiers. The bundle
emits 32 review-only relationship groups:

| Suggestion basis | Groups |
| --- | ---: |
| Same authority and application number | 2 |
| Same authority and normalized address | 15 |
| Same exact WGS84 coordinate | 14 |
| Same non-empty source `SiteId` | 1 |

These signals overlap and are not merges. Fifty-six observations appear in at
least one suggestion, but neither that number nor the application count is a
unique-site count. The unique-site count is deliberately null.

The source advertises applications received since 2012, yet four matched rows
have source `ReceivedDate` years before 2012: 1999, 2007, and two in 2011. The
records are preserved and the discrepancy is reported rather than repaired.

## Numeric and operational calibration boundaries

The ArcGIS metadata does not define a usable unit for `AreaofSite`, `FloorArea`,
`ITMEasting`, or `ITMNorthing`; the release records their unit as
`unknown_source_unit`. `NumResidentialUnits` is a count. `OBJECTID` and
`ORIG_FID` are identifiers, not quantities. In the matched rows, both ITM fields
and `ORIG_FID` are entirely null. No source number is converted into MW, MVA,
annual energy, PUE, workload, or data-centre type.

An official 2026 Enterprise Ireland/KPMG report was used only as restricted
aggregate calibration. It reports, as of 2025, 72 operational grid-connected
buildings across 36 sites and 1,543 MW of installed IT capacity, while excluding
planning-stage projects. The PDF says “KPMG All Rights Reserved.” Its exact byte
size and SHA-256 are pinned in `assessment.json`, but the PDF is not retained.
The three aggregates are not joined to, used to label, or allocated across any
planning row.

## Frozen artifacts and validation

The bundle retains 15 official raw inputs byte-for-byte, including the CKAN
package, service and layer metadata, eight count-only responses, one bounded
matched-feature page, the bounded co-location review page, and rights evidence.
Derived outputs are deterministic JSONL, CSV, schema, summary, relationship
suggestions, assessment, attribution, and README files. A manifest binds every
retained byte.

Core hashes are:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `assessment.json` | 24,941 | `f8f0b1a3006e5b9bda344b40709dec56812a3b469e8b383000cef225ec2bbdc7` |
| `schema.json` | 13,316 | `ad221524b1c22d1e14d5414db112ce86a71f7bcd9766e0e10e8c0d9e0f793e83` |
| `summary.json` | 4,959 | `f15e8054c98f9c8da516b6714490c824e8d6f7cf3c78dc6cd307b851f83dc9ac` |
| `observations.jsonl` | 512,398 | `57e766f1b7151da7ad57ace43da851ccaa452b5731facd79853452a0a6f20c0b` |
| `observations.csv` | 246,551 | `58122c6d42bf8a813123729fab8426b1830cf0eb1dd0d5d80ebd70d21ff0b092` |
| `relationship-suggestions.jsonl` | 9,447 | `9e68e8e9634829d0de43f8cd47c9998a5792c56aab1020163a4f1d77024f855b` |
| `manifest.json` | 4,434 | `f52bd936620909ca948e687164957e0d6510dafda957e778b5d977f5e941128c` |

Validate the frozen release with zero network requests:

```sh
python3 scripts/validate_ireland_planning_release.py
```

Build a new snapshot from the official endpoints:

```sh
python3 scripts/build_ireland_planning_release.py \
  --output /absolute/new/release/path
```

The builder refuses an existing output path. The validator checks the exact
file set, canonical documents, official HTTPS retrieval metadata, CC BY 4.0
rights boundary, source schema, phrase and count contracts, row order, geometry,
date and numeric semantics, relationship-review policy, raw and manifest hashes,
and byte-for-byte offline reproduction of every derived file. Source changes
require a new release ID rather than silently mutating this frozen snapshot.

## Limitations

- The source is a merged set of participating local-authority registers, not a
  proof of complete Ireland coverage or global coverage.
- Description phrase matching can miss relevant applications and can require
  periodic vocabulary review.
- A planning point is not necessarily a building centroid, campus boundary, or
  unique physical site.
- Planning records do not prove construction, operation, ownership, workload,
  facility type, grid capacity, consumption, or PUE.
- Relationship suggestions require human review and cannot be used as automatic
  entity resolution.
