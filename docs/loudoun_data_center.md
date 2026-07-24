# Loudoun County data-center GIS and assessor calibration

Loudoun County publishes two unusually relevant official GIS layers and a 2026 assessor report.
The Atlas lane is nevertheless limited to metadata and aggregates because the available source
terms do not expressly grant the commercial redistribution rights needed for a public compiled
database.

The frozen assessment is
`source_assessments/loudoun-data-center-2026-07-18-v1/`. It pins official retrieval URLs, byte
counts and SHA-256 digests, full layer schema metadata, two count-only results, three grouped
county-classification distributions, and the assessor report's aggregate table. It contains no
source feature row, parcel identifier, owner, project, permit, feature geometry, or row-level
coordinate. The retrieval timestamp is `2026-07-18T23:00:43Z`.

## Rights decision

The county's [GeoHub page](https://www.loudoun.gov/1776/GeoHub-and-Other-Online-Resources)
describes GeoHub as an open-data platform where users can share, view, download, and map spatial
data. The official [mapping-products page](https://www.loudoun.gov/1774/Mapping-Products-for-Purchase)
says many spatial datasets are available for the county or a selected area at no cost in CSV,
KML, or SHP format.

The two ArcGIS items are public and county-owned by
`Doug.Gibson@loudoun.gov_LoudounGIS`. Their item metadata says the data are available to the
public, intended for use at 1:2400 or smaller, and that acknowledgement of Loudoun County would be
appreciated in derived products. The pipeline item also carries the county's accuracy,
completeness, fitness, warranty, and liability disclaimer.

However, both items have `termsOfUse: null`, blank `accessInformation`, and no standard license
identifier or linked license deed. Neither the pages nor the item metadata expressly grants
commercial use, redistribution of attributes and geometries, derivative-database publication,
sublicensing, or downstream end-user access. Public access and downloadability are not treated as
that grant.

This is a source-governance decision, not legal advice. The result is
`rights_blocked_metadata_and_aggregates_only`: no feature query with `outFields=*`, geometry, or
`outSR=4326`; no raw feature cache; no feature release; and no review leads. Written county
clarification covering the missing rights is required before a new feature-release assessment is
built.

## Live GIS aggregate snapshot

At the pinned timestamp, official anonymous count-only queries returned:

- `Existing_Data_Center_Parcel`, item `ffa967f21077455eaade4f258e3f5326`, layer 1: **139 parcel
  records**;
- `Pipeline_Data_Center_Areas`, item `2a084dcc039249f286685205f1f4b33b`, layer 1: **85 parcel
  records**.

The official layer descriptions define a parcel as a tract or plot of land surveyed and defined by
legal ownership. These records remain parcel records. They are not buildings, campuses,
facilities, physical sites, or a unique-site count, and the two counts are not summed.

The grouped query results are preserved verbatim:

- existing `Data_Center_Status`: `Existing` 139;
- existing `Built_Status`: `BUILT` 103, `BUILT/UNDER CONSTRUCTION` 6,
  `BULT/UNDER CONSTRUCTION` 1, and `UNDER CONSTRUCTION` 29;
- pipeline `FIRST_Status`: `Active` 51, `Approved` 16, and
  `Approved: Conditionally` 18.

`BULT/UNDER CONSTRUCTION` is a source value, not silently corrected. No exact county data
dictionary defining these fields was found in the retrieved materials. The values therefore remain
county classifications for this retrieval snapshot only; they are not automatically promoted to
Atlas lifecycle status. In particular, a pipeline application label is not independent evidence
of physical construction.

## 2026 assessor aggregate calibration

The pinned official
[2026 Loudoun County Data Center Guidelines PDF](https://www.loudoun.gov/DocumentCenter/View/219238/462-Data-Center-2026-Guidelines-PDF)
reports data-center property statistics as of **January 1, 2026**:

| Type | Parcels | Improved parcels | Vacant parcels | Complete data centers | Under construction | Built sq ft | Under-construction sq ft |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Enterprise/Hyperscale (`Enter./Hyper.` in the PDF) | 32 | 15 | 17 | 40 | 9 | 6,693,767 | 1,460,840 |
| Net Lease | 94 | 58 | 36 | 74 | 15 | 11,584,508 | 3,978,866 |
| Retail/Colo | 125 | 78 | 45 | 101 | 13 | 26,032,761 | 3,774,197 |
| **Official total** | **251** | **153** | **98** | **209** | **43** | **44,311,036** | **9,213,903** |

The category rows do not reconcile to every official total:

- improved parcels sum to **151**, while the official total is **153**;
- complete data centers sum to **215**, while the official total is **209**;
- under-construction data centers sum to **37**, while the official total is **43**.
- within the Retail/Colo row, improved plus vacant parcels sum to **123**, while that row reports
  **125** parcels (the official total's 153 improved plus 98 vacant parcels does reconcile to 251).

Parcel, vacant-parcel, built-square-foot, and under-construction-square-foot rows do reconcile.
The bundle preserves the category rows, official total, cross-row sums, within-row parcel
composition checks, deltas, and reconciliation flags separately. It does not repair or choose
between conflicting official figures. The PDF also spells the column heading
`Under Contruction`; that source spelling is noted without changing the numeric meaning.

The assessor table is aggregate calibration only. Its type breakdown and counts are not mapped to
GIS parcel rows. The report's data-center counts are not assumed to be parcel counts, the GIS
snapshots are not treated as equivalent to the assessor snapshot, and no cross-source
reconciliation is attempted.

## Units, power, and energy

The layer schemas preserve source field names that indicate acres and square feet. No source values
were retrieved and no conversion was performed. In particular, `Overall_SQ_FT`, `Proposed_SQ_FT`,
permit square feet, and `FIRST_Overall_SQ_FT` remain source-scoped floor-area fields.

The two layers document no MW, MVA, energy, PUE, or workload field. Neither GIS floor area nor the
assessor's aggregate square feet is converted to power capacity or annual energy consumption.

## Licensed-access unlock path

Before retrieving complete layers, obtain a written county grant that expressly covers both item
IDs and:

- commercial use in a compiled data product;
- local storage and raw-response caching;
- modification and derivative-database creation;
- public display and redistribution of attributes and geometries;
- sublicensing or downstream end-user access;
- attribution and notice requirements; and
- refresh, retention, termination, and deletion terms.

After that grant is documented, create a new assessment ID. Fetch each layer independently through
the official query endpoint with `where=1=1`, `outFields=*`, `returnGeometry=true`, and
`outSR=4326`; paginate deterministically by the source object ID; verify initial and final counts;
reject missing pages and duplicate object IDs; retain and hash every raw response; preserve the
parcel entity unit; and do not auto-merge the two layers.

## Build and offline validation

The network builder refuses an existing output and is structurally limited to official pages,
item/service/layer metadata, the official PDF, two count-only queries, and three grouped-statistics
queries with `returnGeometry=false`. It writes atomically and freezes the finished bundle to
directory mode `0555` and file mode `0444`:

```sh
python3 scripts/build_loudoun_data_center_assessment.py \
  --output source_assessments/loudoun-data-center-2026-07-18-v1
```

The offline validator makes zero network requests and checks canonical JSON, the exact file set,
rights and retrieval boundaries, item and layer identities, all field names, parcel semantics,
aggregate counts and distributions, assessor non-reconciliation, the pinned PDF hash, payload
hashes, the manifest, and its sidecar:

```sh
python3 scripts/validate_loudoun_data_center_assessment.py
```

The assessment SHA-256 is
`d54d04f9b9085a09f8546852b34a1aa10019e17528a3cd6a0924b8cff9710e82`, the schema SHA-256 is
`184ab226cab6f2588c4829048499370c81b491af8a6283b15d9800b9dd161426`, the calibration SHA-256 is
`b1543e6c50abce7981578c0f98a0b019df7e75c27d119e0712d45edae53d6bb8`, and the manifest SHA-256 is
`3c0e524d5b13d428bccd89ca33988945b1d58dba3d8ea1459c86243527401cb4`. The official assessor PDF
SHA-256 is `dfed31cd8b7d2abf2db882595d5d5d6567a9327c2063ca1c75ec043073c75134`.
