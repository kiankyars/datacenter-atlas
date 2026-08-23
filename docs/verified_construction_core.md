# Verified Construction Core

The long-term product target is a compact, public cohort of 100 physical data-centre sites with
linked active construction projects, precise geometry, current evidence, typed power semantics,
and reviewable imagery outcomes. The current artifact is deliberately labelled
[`v0.13 preview`](../verified_construction_core/2026-08-20-preview-v0.13/README.md), because the
available evidence does not yet support that final claim. The previous
[`v0.12 preview`](../verified_construction_core/2026-08-20-preview-v0.12/README.md),
[`v0.11 preview`](../verified_construction_core/2026-08-20-preview-v0.11/README.md),
[`v0.10 preview`](../verified_construction_core/2026-08-20-preview-v0.10/README.md),
[`v0.9 preview`](../verified_construction_core/2026-08-20-preview-v0.9/README.md),
[`v0.8 preview`](../verified_construction_core/2026-08-20-preview-v0.8/README.md),
[`v0.7 preview`](../verified_construction_core/2026-08-20-preview-v0.7/README.md),
[`v0.6 preview`](../verified_construction_core/2026-08-20-preview-v0.6/README.md),
[`v0.5 preview`](../verified_construction_core/2026-08-20-preview-v0.5/README.md),
[`v0.4 preview`](../verified_construction_core/2026-08-20-preview-v0.4/README.md),
[`v0.3 preview`](../verified_construction_core/2026-08-20-preview-v0.3/README.md),
[`v0.2 preview`](../verified_construction_core/2026-08-20-preview-v0.2/README.md) and
[`v0.1 preview`](../verified_construction_core/2026-08-19-preview-v0.1/README.md) remain
byte-frozen and hash-validated rather than being overwritten.

## Preview scope

The preview selects 62 projects attached to 59 source-scoped physical sites in 27 countries from
`2026-07-22-open-seed-v97`. Every project has:

- a physical-status observation no more than 90 days old on the fixed 2026-08-20 cohort lifecycle
  reference date;
- an authoritative physical-status method and an explicit evidence row;
- one reviewed project-to-campus identity link;
- a pinned source record and geometry-evidence key; and
- an official boundary or a source-specific site/address locator with its precision limit.

The e-Stat, Chiba, Census, NSW Planning, firstcolo, NLS, Environment Agency, Kartverket, and OSM
geometry evidence used by the v0.11 through v0.13 deltas was captured and its geometry/identity use
accepted on 2026-08-23. It cannot update lifecycle state after the fixed 2026-08-20 cohort cutoff.
For preview compatibility, the v0.13 manifest and selection report retain
`reviewed_at` as an alias for that lifecycle cutoff and also expose
`cohort_lifecycle_reference_date` and `geometry_identity_reviewed_at` as distinct machine fields.

CoreSite DE3 and Scala SFORPF01 have official parcel or surveyed project polygons. Verne Mäntsälä
uses the exact municipal cadastral polygon of its explicitly linked parent campus; that polygon is
not presented as the footprint of the current 70 MW development. Green Mountain Undheim uses the
deterministic union of official Kartverket parcels 1121-46/316, /317, and /319. It is the approved
project-site parcel boundary, not either data-hall footprint or the observed construction extent.
Thirty-one project rows use points and are labelled by their actual scope: shared-campus reference,
facility reference,
same-parcel infrastructure reference, parcel reference, official address, or first-party campus
location. They are not silently promoted to building footprints or site boundaries.

The v0.6 points include the coordinate printed in AdaniConneX/Pune Data Center Limited's PNQ04
compliance report, accepted only as a `project_locator`; the Hong Kong Lands Department HKG09
address result transformed through its official HK80-to-WGS84 service; and Kartverket's verified
Østre Aker vei 24C address point for Skygard OSL1. The Goodman and Skygard points are
`campus_locator` records, not project or building footprints. Kvandal uses the exact frozen current
Kartverket boundary of parcel 1806-10/760 only as a campus locator after a separate NVE identity
bridge. It is not the 25 MW Data Center 1 footprint, the later 75 MW project footprint, or proof that
the one parcel is the complete Nscale campus.

The v0.6 cohort includes nine project rows—atNorth ICE02 Phase 2, QScale Q01 Building B, Green
ZRH1 DC4, The Barn Saline, Microsoft Mount Pleasant's second facility, Amazon Salem's active
buildout, and STT Jakarta 3, 5, and 6—using contributor-mapped OSM polygon locators (seven
distinct polygons) under a separate authority model. Each is accepted only as a
`community_mapped`
`campus_locator`; none is counted as an official boundary, project/phase footprint, construction
extent, lifecycle observation, or imagery result. The selected geometry locates the named campus,
not necessarily the current building project. QScale retains one reported 60 MW design-stage
critical-IT observation. Saline's 1,400 MW contracted campus grid connection and modeled annual
energy range remain pinned in the bridge for provenance but are not promoted to project power or
measured consumption. Campus operating models likewise do not become project claims. The three
STT rows deliberately share the same STT Jakarta 1 OSM polygon as a campus locator; that polygon is
not any Jakarta 3/5/6 footprint.

The seven-project v0.7 delta adds Colt PAR2, AWS Walqa, atNorth SWE02, Alto SP01, Teraco CT1,
Digital Edge SEL3, and Microsoft San Bovio. Colt carries an official DGFiP cadastral boundary;
San Bovio carries a capture-replayed OSM campus polygon. The other five additions are exact,
source-scoped project or shared-campus locators. SEL3 inherits only its explicitly proven adjacent
SEL2 campus identity, Walqa's blind imagery rejection remains local-unsealed and creates no claim,
and Alto's three workloads plus operator relationship are explicitly `intended`.

The eight-project v0.8 delta adds Digital Realty VIE13, ENKA EDS IST 01, Colt FRA3, Macquarie IC3
Super West Phase 1, Equinix MU4 Phase 3, CDC Laverton, Pure DC LON01 B2, and the Borealis Blönduós
expansion. VIE13 and IST 01 use direct first-party facility-page points as project locators. Six
frozen global-v3 OSM source objects retain their raw geometry identity separately from the curated
publication target: Colt's building polygon is a project locator; Macquarie's source object is a
`project` but is used only for its explicitly linked parent campus; and the Equinix, CDC, Pure DC,
and Borealis polygons are likewise campus locators. Across v0.8, 16 project rows use 14 distinct
community-mapped polygons. None is an official boundary or current construction extent.

Digital Realty VIE13 retains a source-bound `colocation` operating model. CDC Laverton adds one
intended operator claim. Borealis operator and utility strings are explicitly excluded. ENKA's
identity evidence and Macquarie's parent-facility 1.28 design PUE are retained as context-only
evidence; neither creates a project role or metric. The Macquarie project keeps only its scoped
6 MW Phase 1 observation, not the parent facility's 47 MW capacity or design PUE. No v0.8 workload
is promoted, and all eight new projects inherit the default not-reviewed imagery outcome.

The three-project v0.9 delta adds CDC Marsden Park, Digital Realty 330 East Cermak, and the NTT
FRA1 7.3 MW expansion. Marsden Park's capture-replayed OpenStreetMap facility polygon and FRA1's
frozen global-v3 facility polygon are campus locators. Cermak uses the selected OpenStreetMap 330
East Cermak building as a project locator. The City of Chicago building record is identity context
only, and the separate 350 East Cermak objects remain rejected. OpenStreetMap and City lifecycle
tags never create or alter the projects' authoritative construction statuses.

Marsden Park publishes no 504 MW or 1 GW capacity and retains only the intended CDC operator
binding. FRA1 publishes one planned 7.3 MW project-scoped critical-IT observation. Its 70.1 MW
current-campus and 77.4 MW post-expansion campus values remain non-additive context; the source's
120 MVA electrical figure remains untyped. No v0.9 workload is promoted. The downloadable v0.9
README and attribution file reproduce the capture-bound City of Chicago notice, attribution,
canonical terms URL, and additional-terms reminder.

The three-project v0.10 delta adds Oracle Project Jupiter, CyrusOne FRA7, and Colt London 4.
Oracle's frozen global-v3 facility polygon is accepted only as a parent-campus locator. Its raw
OSM source lifecycle and operator tags remain geometry metadata, not project status or normalized
roles. CyrusOne uses the official Hessian FF7 L1 permit coordinate only as a project locator; the
permit, its ETRS89/UTM 32N CRS context, and the derived WGS84 point do not create a parcel,
building boundary, current-work extent, capacity, or lifecycle claim. Colt uses a capture-replayed
exact-name OSM London 4 building polygon only as a project locator.

Only Colt publishes a new metric: planned 31 MW critical IT at the project scope. CyrusOne's
campus-scoped planned 81 MW critical-IT value and Oracle's campus-scoped planned 2,450 MW
generation value and AI workload remain validated source context and are excluded from project
publication. No v0.10 role, operating-model, or workload binding is added. The inherited City of
Chicago notice remains byte-exact in both downloadable public text files, and OSM attribution
covers the inherited and new OSM-derived locators.

The one-project v0.11 delta adds IIJ Shiroi DCC Phase 3 in Japan. IIJ's dated disclosure retains
`under_construction` as of 2026-06-25 and one planned 10 MW project-scoped grid-connection
observation. The source's optional 25 MW expandability ceiling is not a second capacity row and is
not treated as installed, contracted, current, or additive capacity. No operating model, workload,
operator, customer, tenant, user, or owner is inferred for the unfinished phase.

Chiba Prefecture's exact campus-name registry row binds Shiroi Data Center Campus to Sakuradai
5-1-1. That address prefix corresponds textually to the selected official e-Stat feature name,
Sakuradai 5; no address coordinate or point-in-polygon containment is asserted. The complete 2020
census small-area polygon is accepted only as an `official_source` `campus_locator` and remains
`official_boundary=false`. e-Stat warns that statistical small-area boundaries need not match
general regional or administrative boundaries; accordingly, the polygon is not presented as the
IIJ campus, a parcel, the Phase 3 building, a construction footprint, or a current-work extent. It
is the published locator geometry and only the scope of the statistical feature, not a containment
claim about the campus. CSV latitude and longitude retain e-Stat's X/Y values only as the
source-published polygon shape centre and display
anchor; they must not be used without the polygon or treated as an independent campus, project,
or site point. The reported 55,117.019 m² area likewise belongs only to the selected statistical
feature, not to the IIJ campus, site, parcel, building, or construction works.

The five-project v0.12 delta adds CoreWeave Lancaster Phase 1, Lancium Abilene's remaining
six-building expansion, NTT Dallas TX4, QTS York Building 1, and TRG HOU2. Each project is linked
to one distinct parent campus and retains its dated source status. Census Public_AR_Current
exact-address matches are used only as street-range campus locators. They are not parcel,
cadastral, campus, building, project, or construction boundaries; they do not prove containment;
and their numeric horizontal uncertainty is unknown. NTT's current 2060 Lookout Drive address and
the Texas TDLR record's conflicting 2008 address both remain disclosed. QTS's 2143 Hands Mill
Highway address is scoped only to the parent York campus, never to Building 1. No v0.12 metric,
role, workload, operating model, imagery result, or party claim is added.

The six-project v0.13 delta adds Goodman SYD01, firstcolo FRA7, XTX Kajaani DC2, QTS Cambois
earthworks, Bitzero Namsskogan's power-infrastructure expansion, and Ezditek RUH01 Phase 1. All six
represent distinct physical sites. Goodman, firstcolo, and QTS use source-reported points; QTS uses
only the wider-campus NGR point, not the separate Phase A point. XTX and Bitzero use official NLS
and Kartverket cadastral polygons only as parent-campus locators with `official_boundary=false`.
RUH01 uses an exact-name OpenStreetMap building polygon as a community-mapped, non-official
locator. None of these geometries establishes a construction extent, project footprint, capacity,
role, workload, energy, efficiency, or lifecycle claim. Raw all-rights PDFs and issuer HTML and all
Esri imagery remain excluded; the tracked capture contains only compact facts, derived geometry,
byte counts, hashes, and source-specific rights.

The review contract distinguishes `direct_geometry` from `coordinates_to_point` and records
whether geometry comes from the project or its parent campus. Coordinate serialization adds no
precision. The maincubes BER02, AVAIO Taurus, and KAO KLON-03 points retain unknown horizontal
accuracy. Scala Huechuraba and Lampa use official Chilean environmental-review representative
points with conservative 50 metre analyst envelopes; neither is presented as a footprint.

The project status field is `last_observed_physical_status`, not an inferred current state. The
preview leaves `independent_imagery_verification=false` for every row. Eight inherited projects
have a non-default satellite-review outcome, but those reviews create no lifecycle claim. Six are portable
identity-bound records; two preserve an identity mapping extracted from exact local hash-bound
lineage that is not independently available in a clean clone. Saline retains only its tracked v57
visible-change follow-up verdict; an unsealed later review is not published as project evidence.
Microsoft and Amazon retain uncertain v57 outcomes. BER02's later conflicting blind verdict and
KAO's later conflicting verdict remain unsuperseded rather than being resolved in favor of either
judgment.

Undheim adds one explicit `publisher_contractor_drone_context` record linked to Backe's project
page. It redistributes no image bytes and is not a blind, satellite, or independent review. The
validator forbids using it for geometry, status, capacity, progress, or building count.

## Files and semantics

- `projects.csv` preserves project-level status, geometry source entity, derivation, method and
  scope, coordinate precision, source URLs, typed power observations, and explicit
  unknown/not-estimated reasons.
- `sites.csv` groups the 62 selected projects into 59 physical-site keys without claiming
  global cross-source deduplication.
- `evidence.csv` is the closed set of 145 status, geometry, operating-model, context, workload, role, and
  typed-metric evidence rows referenced by the cohort.
- `sites.geojson` and the dependency-free `map.html` expose the same 59 site IDs. The visible map
  footer credits every selected geometry provider whose terms require it.
- `schema.json` defines CSV fields, logical types, keys, embedded evidence references, GeoJSON
  geometry equality, and the map dependency in machine-readable form.
- `selection-report.json` accounts for all 531 source pipeline rows and records every final gate.
  It also carries the exact non-default imagery-review provenance and unresolved conflicts.
- `manifest.json` and `manifest.sha256` bind the complete preview inventory.

## Version policy

Each preview is a coherent frozen snapshot, not a separate pile of data that must be added to the
latest CSV. v0.13 inherits the byte-frozen v0.12 artifact and adds six independently pinned sites;
v0.12 inherits the byte-frozen v0.11 artifact and adds five independently pinned U.S. projects with
Census address-match campus locators; v0.11 inherits v0.10 and adds IIJ Shiroi Phase
3; v0.10 inherits the byte-frozen v0.9 artifact and adds three independently pinned
projects; v0.9 inherits the byte-frozen v0.8 artifact and adds three; v0.8 inherits the byte-frozen
v0.7 artifact and adds eight; v0.7 inherits the byte-frozen
v0.6 artifact and adds seven; v0.6 inherits all 21 reviewed
v0.5 decisions through an exact base contract hash and
adds eight projects across six physical sites; v0.5 inherits all 17 reviewed v0.4 decisions and
adds four reviewed geometry bridges; v0.4 inherits the 15 reviewed v0.3 decisions and adds two;
v0.3 inherits the 12 reviewed v0.2 decisions and adds three. Users normally consume only the latest
preview; the older artifact remains because it proves what the product said at that date and lets a
historical result be audited against the code commit that produced it.

Missing development type, operating model, workload, power, annual energy, PUE, or WUE never
becomes zero. Reported observations preserve metric, stage, units, interval, method, confidence,
and evidence. PUE/WUE stay separate from power; annual energy remains unestimated unless scoped
inputs and assumptions exist.

Workload values are evidence-linked source classifications, not proof of an operating workload.
Every observation has a validator-bound `deployment_scope`; all eight current observations are
`intended`. Every published role has a machine-readable evidence ID and relationship scope. Nine
intended-operator and two intended-customer claims pass. Four prior CDC/AST owner or operator
strings plus the atNorth, QScale, Microsoft, and Amazon project-operator candidates lack
role-specific evidence, so the current preview clears them and records the exclusions and reasons
instead.

## Validation and rebuild

Validation and byte-exact rebuilding work in a public clean clone from the generated preview and
89 manifest-listed portable inputs. The ignored v97 and v14 payloads are optional, all-or-nothing
hydration-only cross-checks; when all five are present, their exact embedded source rows are replayed
as an additional validation layer:

```sh
uv run python scripts/build_verified_construction_core.py --validate-only
uv run python -m unittest -v \
  tests.test_verified_construction_core \
  tests.test_verified_construction_core_v012 \
  tests.test_verified_construction_core_v013
```

The builder refuses to overwrite an existing directory:

```sh
uv run python scripts/build_verified_construction_core.py \
  --output-dir /tmp/verified-construction-core-preview
```

## Final-release gates

The preview cannot be promoted to v1 until it has exactly 100 resolved sites and linked projects,
at least 40 countries, at least 50 non-US sites, no country above 40% of the cohort, a recorded
imagery outcome for every selected project (and therefore every site), a blind 20-row re-review with at least 19 identity/construction
agreements, and a byte-exact clean-clone rebuild from publicly available inputs.

The next research tranche should start with fresh authoritative project rows in countries absent
from this preview, resolve an official parcel/site/address geometry, then execute dated imagery
review where usable scenes exist. Locality/model centroids remain rejected; an official project
representative point is usable only as an explicitly labelled locator with an uncertainty envelope.
Announcement, permit, catalog completion, or automated pixel change alone does not satisfy the
physical-construction gate.
