# Current coverage ledger

The authoritative machine-readable inventory for the frozen v9 scope is
`current_coverage_ledgers/2026-07-19-v9/current-coverage-ledger.json`. The v1 through v8 bundles
remain preserved historical checkpoints. V9 pins exactly 40 artifacts: 34 public/open and six
local/restricted. Relative to v8, it replaces exactly five current artifacts: construction
master/map v12 with v13, public federation v10 with v11, coverage audit v11 with v12, and open-seed
v30 with the promoted public-stack v32. The other 35 entries, including cumulative Unknown030,
remain unchanged. Replacement counts are not additive across versions.

The promoted source release v32 contains 370 source-scoped entities (216 campuses and 154
projects), 226 exported evidence records, 252 database evidence observations, 401 typed metric
observations, 195 pipeline rows, 161 construction-source signals, and four advisory resolution
candidates. It has 139 coordinate-bearing entities. Relative to v30 it adds 11 campuses, 11
projects, 11 exported evidence records, 13 database evidence observations, 11 pipeline rows, eight
signals, and 11 current `under_construction` lifecycle observations. It adds no normalized metric,
coordinate, geometry, workload, operating model, or role. These entity and observation counts are
not unique-site counts.

The ledger is deliberately not a site total. It records 29 artifacts eligible under their
upstream terms, five metadata-only assessments that release no source rows, and six quarantined
artifacts. It also separates publication form:

| Publication mode | Artifacts | Meaning |
| --- | ---: | --- |
| Public row release | 5 | Versioned rows are public, but their declared record unit still governs interpretation. |
| Public index or audit | 4 | References, crosswalks, and coverage gaps; no child-row or site-total claim. |
| Public review or discovery | 20 | Candidates, planning observations, footprints, news, satellite, or other review controls. |
| Public metadata or aggregate only | 5 | Assessment facts and permitted aggregates; zero source rows released. |
| Local quarantined | 6 | Useful only in restricted research pending rights clearance. |

Across every mode, `unique_physical_site_count` remains `null`, global completeness and benchmark
parity remain false, and counts from separate artifacts are not additive. Parcel, application,
permit, footprint, planning-observation, candidate, catalog-job, link, and review counts are never
converted into facilities or construction arithmetic.

## Public construction master and map

Construction master v13 contains 109,107 observation rows: 315 Tier A, 6,298 Tier B, and 102,494
Tier C. Only the 315 Tier-A source-supported observation rows enter construction arithmetic:

| Source-supported status | Rows |
| --- | ---: |
| Under construction | 226 |
| Expansion | 27 |
| Proposed | 22 |
| MEP / electrical | 15 |
| Site preparation | 9 |
| Shell | 6 |
| Announced | 3 |
| Permitted | 3 |
| Civil works | 2 |
| Foundations | 2 |

These 315 rows are not 315 unique sites, and zero have been independently re-verified by a
master-level review. The remaining 108,792 master rows stay explicitly review-only: 6,130 fuzzy
leads, nine SEC filing leads, 114 Irish, three England, 13 Netherlands, three New Zealand, four
France, and 22 NSW planning or environmental-review observations, 102,451 structural candidates,
and 43 selected historical algorithm-v1 analyst imagery-review rows. Those units are not added to
the Tier-A arithmetic.

Relative to v12, the exact 11-row v13 delta comprises only coordinate-null project observations,
all `under_construction`. It adds no normalized capacity, annual energy, PUE, untyped power,
workload, operating model, role, geometry, or independent verification.

The historical v11-to-v12 33-row delta comprised only project observations: 29
`under_construction` and one each `permitted`, `proposed`, `shell`, and `site_preparation`. Only
maincubes BER02 carries source coordinates; the other 32 are coordinate-null. Five additions
preserve source-reported planned `critical_it_mw`: 48, 18, 20, 25, and 7 MW. Planned critical IT is
not measured operating consumption. The delta adds no annual energy, PUE, untyped power, operating
model, or independent verification. It adds four broad `ai_specialized_unspecified` workload
observations and one `crypto_mining` observation; none is copied to another row.

The master preserves 115,402 source-evidence records and sparse source metrics rather than filling gaps. It contains 233 typed-capacity
evidence observations excluding annual energy and PUE, 73 annual-energy evidence observations, two
PUE observations, 23 untyped power statements, 103 workload observations, and two operating-model
observations. At the master-row level, 94 rows have capacity, 46 annual energy, two PUE, 82
workload, and two operating-model rows. Evidence-observation counts and row-presence counts answer different
questions and are not added.

The public map is a presentation derivative of the same master. It maps 108,973 observation rows
and leaves 134 without coordinates. Its mapped tiers are A 199, B 6,280, and C 102,494; the default
A+B view therefore contains 6,479 mapped observations. Another 102,541 mapped rows retain an
unknown-country label. Map rows must never be added to master rows or interpreted as unique sites.
The 11-row v13 master delta adds no mapped rows.

Within-release resolution contributes 8,586 advisory links, with zero accepted relationships,
zero automatic merges, and unique sites `null`. Construction master v13 pins current public
federation v11 and coverage audit v12 as contextual inputs. Federation v11 reports 15,795 arithmetic
child-release rows—9,665 non-review and 6,130 review-only—plus 6,445 pipeline records, 13,239
evidence records, 1,187 capacity observations, 100,409 resolution candidates, 98 source-family
entries, and unique physical sites `null`. Coverage audit v12 reports 441 coverage groups and 2,411
open gaps. Neither federation, audit, resolution links, nor their children
become master rows or sites.

## Satellite and computer-vision progress

The Sentinel queue has 6,830 disjoint priority jobs. Current catalog state is:

| Priority lane | Selected | Complete | No scene | Pending | Failed |
| --- | ---: | ---: | ---: | ---: | ---: |
| Active construction | 74 | 65 | 9 | 0 | 0 |
| Proposed pipeline | 20 | 16 | 4 | 0 | 0 |
| Unknown, cumulative v030 | 6,736 | 4,350 | 300 | 2,086 | 0 |
| **Queue total** | **6,830** | **4,431** | **313** | **2,086** | **0** |

Unknown030 is the sole cumulative unknown-priority progress artifact. Unknown001 through Unknown029
overlap it and are not additive. Its `incomplete` state is intentional: this is a bounded
catalog-only checkpoint with 2,086 jobs still pending, not a completed global queue. It ran no
computer vision or change analysis, mutated no atlas claim, and inferred no identity, lifecycle,
operating status, or power. A completed catalog job establishes scene availability, not visible
change or a data-centre fact.

The separate frozen v2 change qualification processed five active-001 scene pairs into five
machine-proposal bundles with zero failures. Two bundles use the same Virginia AOI and byte-identical
comparison image, while two South Carolina AOIs overlap. All five were visually inspected but have
no analyst-decision artifact; they are not distinct-site, identity, lifecycle, construction, type,
capacity, power, PUE, workload, or energy facts and remain outside public federation v11, master
v13, map v13, candidate-fusion v13, and calibration. They do not alter ledger v9 construction
counts.

Three later active-lane checkpoints add 8, 9, and 21 completed algorithm-v2 proposal rows, and a
bounded edge-scene reselection adds another 15 rows across nine previously unprocessed AOIs. Together
with the five-job qualification, the current v2 inventory is 58 unique queue rows across 40 exact AOI
geometries, all unreviewed and outside public federation v11, master v13, map v13, candidate-fusion
v13, and calibration. Ledger v9 inventories the proposal artifacts without importing their rows as
construction or site claims.
The 65 completed active catalog rows partition by current output as 58 v2 proposal rows, five
historical-v1-only rows, and two France rows with no change output. Seven active rows have historical
v1 reviews, including two also present in the new v2 set, but changed selected-scene hashes prevent
label transfer. This is evidence-state accounting, not site counting.
“Full-cover” in this lane means that the selected imagery assets cover the required native read
windows; it does not mean every AOI pixel is clear or valid.

Candidate-fusion v13 examined 102,451 structural candidates and emitted 14,324 candidates with at
least one review opportunity. Its priority tiers are 28 retained-visible-change follow-ups, 1,037
distinct source-root opportunities, and 13,259 shared-root or queue opportunities. Catalog-state
links are 5,352 complete, 18,772 pending, and 295 unavailable because no scene was found. The 43
selected historical algorithm-v1 analyst reviews contain 12 retained follow-ups and 31 rejections; candidate-AOI link
outcomes are 33 retained and 130 rejected. One analyst AOI can overlap multiple candidates, so link
counts are not review-decision, catalog-job, or site counts. Fusion v13 is frozen at Unknown015; its
catalog-link counts are historical and are not additional to the current Unknown030 batch.

Calibration v4 audits the same 43 selected historical algorithm-v1 review pairs. It is a non-random
descriptive audit with no recall denominator, no accuracy-generalisation basis, no production
threshold, and no pixel- or construction-truth claim. The 12 retain and 31 reject decisions are
site-aligned follow-up labels, not lifecycle facts or unique sites, and they do not calibrate v2.
Two active-lane inputs at queue positions 27 and 60 used clipped selected-asset coverage. That does
not support a naive 41-row recalculation: a v2 calibration requires all 43 rows to be reprocessed and
re-reviewed under the current algorithm.

The later algorithm-v2 rerun now accounts for all 43 exact specifications in ten immutable shards:
36 completed numerical comparisons and seven explicit `multi-tile mosaic required` failures. The
frozen [label-blind numerical aggregate](satellite_calibration_aggregate.md) preserves that complete,
disjoint partition and imports zero historical labels. It is outside public federation v11, master
v13, map v13, and candidate-fusion v13. Ledger v9 inventories the aggregate artifact without
promoting any row; it performs no adjudication and changes no construction, site,
field-completeness, accuracy, or calibration count. Its manifest SHA-256 is
`a1b9b2e76dc4efac8ca77edfec7bb6ca2c2457eaa5395958796acf42729dbca4`.

The later frozen [identity-blind rereview audit](satellite_calibration_v2_blind_rereview.md)
assigns fresh image-only decisions to the 36 ready rows: 16 retain, 19 reject, and one uncertain.
Its fixed basis is 28 A/B agreements, seven two-of-three majorities, and one three-way uncertain;
historical labels were joined only after those decisions closed. Thirty of 35 binary-comparable
rows share the prior analyst label (85.71428571428571% raw agreement). This descriptive comparison
is not accuracy, precision, recall, truth, production calibration, threshold validation,
construction truth, or SemiAnalysis parity, and it changes no coverage-audit v12,
construction-master v13, construction-map v13, or current-ledger v9 scope count. The seven
multi-tile rows remain blocked without v2 decisions. V4, manifest SHA-256
`be0e7042eac7a54697ff526400537fe66211dbbdf7d5a505c541a3a6fc4b590d`, is byte-preserved as rejected
historical evidence after an independent audit reproduced a normal-success parent-fsync target
substitution that returned a false release ID. The independently accepted v5 successor has
manifest SHA-256
`dff606bfbd4015c51d24387d4b9a73a48b236895d745b7343aacfe46a5ef57e7`. Fresh QA reproduced the
frozen bytes through API and CLI publication, verified all source and builder pins plus scientific
arithmetic, exercised explicit I/O failures, found no descriptor leaks, and preserved v1 through
v4. V5 re-proves the descriptor-bound parent, target, and exact frozen tree after the
publication fsync. Recovery performs no recursive deletion, preserves unrelated substitutions,
fsyncs every entry mutation, and reports primary and recovery failures together. V1 through v4 and
the review arithmetic remain byte-identical.

The separate accepted frozen [multi-tile mosaic preparation](satellite_mosaic_preparation.md) v6
successor accounts for the seven blocked numerical rows as six metadata-ready specifications and
one still-blocked MRS5 row, with 40 exact input-file pins and zero imagery downloads, imagery opens,
or mosaic executions. V1 through v5 remain byte-preserved rejected publication-mechanics evidence.
V5 fixed v4's mkdir and final-close defects, but its writer and validator acquisition helpers could
open a descriptor and fail before the outer cleanup ledger owned it. V6 registers each descriptor
immediately after open, attempts cleanup after acquisition failures, aggregates primary and cleanup
errors, and always reports the exact requested target plus every allocated staging path. Its
manifest SHA-256 is
`f0cb59766c68e7cc54da8f103f7a92a7eb4943e2fe4533702df9d19c0cd366e6`. A fresh independent audit
reproduced every frozen byte through socket-denied API and CLI publication, reconciled every pin,
found no false success or descriptor growth across seven fault scenarios, and passed the 67-test
v1-v6 lineage. Preparation metadata creates no identity, lifecycle, construction, type,
operator, capacity, power, energy, PUE, workload, calibration, accuracy, or SemiAnalysis-parity fact
and changes no coverage-audit v12, construction-master v13, construction-map v13, or current-ledger
v9 scope count.

The Microsoft Global ML Building Footprints lane is a lawful CDLA-Permissive-2.0 review source. Its
global index has 30,344 Location-plus-LOD9-quadkey shard pointers, 30,344 unique Location/QuadKey
pairs, 30,344 URLs, 225 locations, and approximately 122,423,557,613 advertised compressed bytes.
Four selected shards contain 476,989 source building footprints; 671 footprints intersect the four
bounded construction-prior AOIs. Selected height and confidence presence are both zero, and facts
establishing data-centre identity, type, status, capacity, power, or energy are zero. Index pointers
and footprints are not facility or unique-site rows and do not enter construction arithmetic.

The other bounded public pilots remain review-only: Overture Memphis building candidates, Google
Open Buildings Temporal model signals, GDELT news triage, the OSM fuzzy crosswalk, and the public
SEC filing-derived EdgeMode leads.

## Source-assessment rights ledger

| Source lane | Publication state | Exact current result |
| --- | --- | --- |
| England planning | Public review/discovery | 100,627 source rows yielded four exact-phrase observations: three direct-scope and one context-only exclusion. Optional additions 0; construction evidence, promotion, and recall claims false. |
| NSW major projects | Public review/discovery | 44 list rows comprise 35 base projects and nine modifications. There are 22 active details (19 base and three modifications) and 10 untyped power-statement rows; construction-verified rows 0, typed power/energy promotion false, and unique sites `null`. |
| Netherlands KOOP | Public review/discovery | 20 official-publication query records yielded 13 direct project-review candidates and seven ancillary-context exclusions. Rights gate passed; review-only true; construction evidence and promotion false; accepted relationships and automatic merges 0; unique sites `null`. |
| New Zealand Fast-track | Public review/discovery | Two direct project candidates plus one prior related observation produce three proposed review observations. Rights gate passed; construction evidence false; typed capacity, power, annual energy, and PUE 0; accepted relationships and automatic merges 0; unique sites `null`. |
| France IGEDD/Ae | Public review/discovery | Three direct data-centre project observations plus one ancillary grid-connection follow-up produce four master review rows. The derived rows are publication-eligible, but PDFs are not redistributed, regional MRAE coverage is excluded, and opinions, unit multiplicity, grid, backup, and battery figures are not promoted beyond their source meaning. |
| Meta newsroom fleet update | All-rights-reserved derived curated inputs; introduced by open-seed v20 and retained in current v32/master v13/map v13 | One hash-bound April 28, 2026 official disclosure explicitly names Richland Parish, Lebanon, El Paso, and Tulsa as under construction. Four project rows and four locality-level campus rows share one evidence observation; coordinates are approximate named-locality centroids. Typed capacity, annual energy, PUE, and automatic site merges are 0. The master/map imports the four project rows only; it does not copy campus-only operating-model observations onto those projects. |
| Microsoft official news, Finland pages, and current Local project updates | All-rights-reserved derived curated inputs; introduced by open-seed v20 and retained in current v32/master v13/map v13 | Two U.S. project rows retain one source-reported under-construction Mount Pleasant project and one announced Pecos project. The current seed retains three Finland campuses and six phase-specific projects: four source-reported construction phases and two permit-only phases. Its Microsoft Local records add ten coordinate-free campus/project pairs: four `site_preparation`, two `foundations`, three `mep_electrical`, and one `civil_works`. All 16 Finland and Local project rows enter Tier A in master v13; map v13 maps the six Finland rows and records the ten Local rows as coordinate-null. They add no typed capacity, annual energy, PUE, untyped power, operating model, role, independent verification, completion, operation, or unique-site claim; forecasts stay unpromoted, East Point is excluded, and the greater-than-200 MW Finland PPA is portfolio procurement rather than site capacity. Raw source bodies are not redistributed. |
| Vantage and NTT location pages/brochures | All-rights-reserved derived curated inputs; introduced by open-seed v20 and retained in current v32/master v13/map v13 | Five campus and five project rows add KIX1, KUL2, OH1, Frankfurt 1, and Amsterdam 1. Only Frankfurt's sourced 7.3 MW expansion has a current construction lifecycle; it enters Tier A in master v13 and remains coordinate-null in map v13, while four stale or forecast-only project narratives remain lifecycle-null and outside the master. Ten typed critical-IT observations in the seed keep planned, forecast, operational, and superseding scopes separate. KUL2's newer 436 MW planned value supersedes rather than adds to 256 MW; MVA remains metadata; no 42.7 MW Amsterdam value is derived; and source-reported 77.4 MW Frankfurt maximum is not recomputed. OH1's marker is campus-only, both NTT rows reject an impossible reused map coordinate, and roles, operating models, workloads, automatic merges, and unique-site claims remain empty. |
| QTS, STACK Infrastructure, Digital Realty, CyrusOne, and Colt current construction pages | All-rights-reserved derived curated inputs; introduced by open-seed v20 and retained in current v32/master v13/map v13 | Thirteen coordinate-free campuses and 15 project rows add 11 `under_construction`, two `shell`, one `civil_works`, and one `site_preparation` observation. The master imports 14 of those project rows plus the Dugny campus as 15 Tier-A observations; all 15 remain coordinate-null in the map. The only typed additions are planned critical IT scoped to Colt London 4 (31 MW), CyrusOne MIL1 (27 MW), Digital Realty's full three-facility Dugny campus (176 MW), and nominal approximately 16 MW FRA20. Rounded, component, park-buildout, battery, PUE, current-load, energy, tenant, completion, operation, merge, and unique-site readings remain excluded. QTS Cedar Rapids is a likely overlap with an Epoch row, but remains unresolved and creates no automatic relationship. |
| Amazon Pennsylvania innovation campuses | All-rights-reserved derived curated inputs; introduced in v13-or-earlier lineage, retained by open-seed v20, and retained in current v32/master v13/map v13 | Amazon's project pages explicitly label Salem Township and Falls Township as active construction. Each becomes one campus plus one project at an approximate locality point; neither imports the portfolio PPA as site-exclusive capacity, and typed power, annual energy, PUE, and automatic merges remain 0. |
| Amazon Energy Way and SBN100 | All-rights-reserved company and government-record derived inputs; introduced in v13-or-earlier lineage, retained by open-seed v20, and retained in current v32/master v13/map v13 | Amazon's groundbreaking supports active physical construction at Energy Way; Richmond County and NC DEQ records establish county and exact-address context only. A separate Indiana IDEM record directly observes SBN100 construction underway without transferring that status to other permit buildings. No portfolio quantity is converted into site load, energy, or PUE. |
| Aragón government AWS Walqa update | Government-news derived curated input; introduced in v13-or-earlier lineage, retained by open-seed v20, and retained in current v32/master v13/map v13 | The government update explicitly says construction of an AWS data centre at Walqa. The separate locality record adds no typed power, annual energy, PUE, operating model, or automatic merge and is not conflated with other Aragón AWS projects. |
| Related Digital and DTE Saline disclosures | All-rights-reserved derived curated inputs; introduced in v13-or-earlier lineage, retained by open-seed v20, and retained in current v32/master v13/map v13 | Related establishes active physical construction of all three Saline Township buildings. DTE separately supports only 1,400 MW of contracted `grid_connection_mw` and a row-labeled modeled annual-energy interval; neither metric is IT load, gross facility load, generation capacity, PUE, or metered energy. |
| NEXTDC SC2 | Council-investment-news derived curated input; introduced in v13-or-earlier lineage, retained by open-seed v20, and retained in current v32/master v13/map v13 | Sunshine Coast Council explicitly reports SC2 under construction. The row retains broad AI-specialized workload only; no capacity, cooling, PUE, or energy metric is imported. |
| KAO KLON-03 | Environment Agency supporting-document plus Infratil/NZX derived curated input; introduced in v13-or-earlier lineage, retained by open-seed v20, and retained in current v32/master v13/map v13 | A dated 2025 engineer walkover and a May 2026 exchange filing establish physical works and current construction continuity. The project imports no role, workload, capacity, PUE, annual energy, or completion claim. |
| Applied Digital | SEC and ND DEQ derived curated inputs; introduced in v13-or-earlier lineage, retained by open-seed v20, and retained in current v32/master v13/map v13 | Five physical projects retain 600 MW contracted and 300 MW planned `critical_it_mw`. A separate calculated 576 MW row remains planned backup-generation nameplate from 192 proposed 3 MW generators; it is not load, consumption, grid service, or annual energy. |
| Official-source v14-v20 tranches | Company, government, exchange, and utility derived inputs; historical v20 checkpoint retained in current v32/master v13/map v13 | Relative to v13, historical v20 added 42 coordinate-null campuses and 46 coordinate-null projects: 27 `under_construction`, 12 `mep_electrical`, three `shell`, three `site_preparation`, and one `announced`. The seed's 30 typed additions remain split into 27 planned critical-IT, one planned generation-nameplate, and two contracted grid-connection observations; the master imports 24 of the critical-IT observations and the 380 MW CyrusOne Freestone grid-connection observation. The remaining generation, grid, campus-combined, component, portfolio, and greater-than wording is not converted into facility load or operating consumption. Within the v20-only Khazna/Yondr tranche, only Khazna QAJ1 retains a 100 MW planned critical-IT observation and broad AI workload; Equinix DB7x alone retains a retail-colocation operating model. All 46 projects remain unmapped rather than being geocoded. |
| Official-source v21-v30 tranches | Company, government, exchange, filing, and official-news derived inputs; historical v30 checkpoint retained in current v32/master v13/map v13 | Relative to v20, historical v30 added 33 campuses and 33 project observations. The master imports the 33 projects: 29 `under_construction` and one each `permitted`, `proposed`, `shell`, and `site_preparation`. Five projects preserve planned critical-IT observations; four preserve broad AI-specialized workload and one preserves crypto-mining workload. Maincubes BER02 alone carries source coordinates and maps; the other 32 remain explicitly unmapped. Seed-level generation, grid, portfolio, component, and untyped power wording stays separated and is not converted into current operating load, consumption, energy, or PUE. |
| Official-source v31-v32 tranches | Company, government, official-news, and official social disclosures; current open-seed v32/master v13/map v13 | Relative to v30, the promoted seed adds 11 campuses and 11 projects. The master imports all 11 projects as source-supported `under_construction` observations; all remain coordinate-null and add no mapped rows. The delta adds no normalized capacity, annual energy, PUE, untyped power, workload, operating model, role, geometry, independent verification, automatic merge, or unique-site claim. |
| EdgeMode | Public SEC review; direct website blocked | 9 SEC-derived project leads; 0 construction-verified and 0 typed-capacity rows; unique sites `null`. |
| PeeringDB | Public metadata only; source rows blocked | Facility count at probe 5,857; 1 row requested/returned, 0 values retained or released; written permission absent. |
| Cleanview | Public metadata only; API and rights blocked | Non-current 2024 example count 1,176; live count `null`; 0 facility leads and 0 source rows. |
| PJM large load | Public metadata only; source content blocked | 42 retrieval metadata records: 31 PDFs and 7 workbooks; 0 source project rows, numeric values, facility leads, or unique sites. |
| EPA ECHO/FRS | Local quarantined review | Broad NAICS screen 928 rows and 4 name-token leads; 0 publication-eligible, construction, capacity, energy, PUE, or workload rows. |
| PWC Build-Out | Public metadata only; layer rights blocked | 243 building, 72 campus-project, and 61 planning-application records, kept as three non-additive entity levels; unique sites `null`. |
| Virginia DEQ | Local quarantined review | 198 issued-permit rows and 1 application-under-review row; 0 publication-eligible, construction, capacity, or energy rows. |
| Ireland planning | Public CC-BY-4.0 row release | 114 planning observations, 112 authority/application keys, and 32 advisory relationship groups; unique sites `null`. |
| Loudoun County | Public metadata and aggregates only | 139 existing and 85 pipeline parcel records, not summed; no feature rows, attributes, geometry, or unique-facility count. |
| Microsoft buildings | Public review/discovery | 30,344 shard pointers and 671 bounded AOI footprint rows; 0 data-centre facts, as detailed above. |
| Malaysia KPKT OSC 3 Plus | Public metadata only; source traversal rights blocked | 6 controlled access/rights requests; 0 calendar, meeting-page, or result-bearing requests and 0 source rows. All result, agenda, project, site, classification, and metric counts are `null`; Malaysia, Johor, and Selangor completeness are false and DBKL remains uncovered. |
| Singapore BCA Green Mark | Public Open-Data-Licence review release | 4,793 voluntary-certification observations yield a closed 101-observation data-centre union and 4 provisional-letter leads. Certification is not physical lifecycle evidence; project and unique-site counts are `null`, and construction, power, energy, PUE, operator, type, and coordinates are not inferred. |
| Singapore URA Planning Decisions | Public metadata only; credentials absent | 7 controlled audit requests; the two HTTP 200 API probes were application errors, not successful zero-row results. Result-bearing requests and source rows are 0; all decision, project, site, classification, and metric counts are `null`. |
| India PARIVESH environmental clearances | Public metadata-only rights audit; proposal-row rights unconfirmed | 8 controlled rights/access metadata requests; proposal-search, result, detail, document, and data-file requests are 0, source rows are 0, and observed coverage dates plus all source counts are `null`. The separately open 2022 data.gov.in resource is a 386-byte state aggregate, not a project source. |
| Thailand ONEP Smart EIA approved reports | Public fail-closed snapshot audit; outside v9 | 4 controlled GETs total, including 1 JSON snapshot request. The response advertised 13,793 records over 138 pages but returned 94 page-1 rows, including 3 future-dated approvals. Pagination and document/detail/UI traversal are 0; observations, review shards, and imports are 0. The catalogue's literal `Creative Commons Attributions` label is preserved without inventing a version or extending it to report documents. |
| Denmark Plandata.dk local plans | Public review-only planning assessment; outside v9 | The clean 35-request capture completed all 27 exact WFS name queries and retained 5 adopted-layer planning observations from 5 memberships; proposal and cancelled matches were 0. The full task used 67 direct local GETs, including 32 discarded non-evidence probes; only the clean capture is paced and hash-bound. Planning adoption is not construction, documents/PDFs are unrequested, all physical status/type/metric/site counts remain unknown, and imports are 0. |
| [Japan MOE casebook](japan_moe_casebook.md) | Public auxiliary review release; outside v9 | Nine overview rows and eight detail cases reconcile to 10 case observations: 7 matched, 2 overview-only, and 1 detail-only. These are not 10 physical sites; unique physical sites remain `null`. The lane retains 24 scoped effect metrics and 6 program observations, while physical identity, lifecycle, type, IT load, power capacity, PUE, and annual electricity consumption remain null. EcoKaku's unqualified MWh figures are not annualized; the printed Kanden/IIJ `1.1 MWh/year` value is preserved with an internal-consistency warning. Construction-master, construction-map, and current-coverage-ledger imports are 0. |

The metadata-only assessments are public because they contain assessment facts and permitted
aggregates, not because the underlying source rows are redistributable. England, NSW, Netherlands,
New Zealand, and France observations are public review units and do not promote construction or
typed facility facts beyond their declared source semantics. EPA and Virginia records remain local
because their exact row-level publication basis was not established. The complete Scrutica release,
its crosswalk, and their four-layer federation/audit controls also remain local and contribute
nothing to public totals.

Spain BOE, Italy MASE, Brazil PNCP, Germany UVP, Finland LVV, Denmark Plandata, Poland
GDOŚ/SIOS/Ekoportal, South Korea EIASS/NIER, Japan MOE, Malaysia KPKT, Singapore BCA,
Singapore URA, India PARIVESH, Thailand ONEP, IAAC, Chile SEA, and Australian EPBC assessments
remain explicitly outside the v9 current ledger. Their exclusion does not relax any rights,
record-unit, access, restriction, quarantine, or no-import contract elsewhere in the Atlas.

## Explicit parity gaps

V9 records six machine-readable gaps:

| Gap | Status | Consequence |
| --- | --- | --- |
| Benchmark parity | Not computed | No licensed row-level external denominator is pinned. The 43 selected historical-v1 labels provide neither recall nor SemiAnalysis-equivalent precision, feature, or field parity. |
| Global construction coverage | Partial | Expanded public sources, the England, NSW, Netherlands, New Zealand, and France review lanes, structural search, footprints, and satellite review still do not establish a global census. |
| Rights-blocked source lanes | Rights blocked | Public planning, permit, and environmental-opinion observations do not resolve separate commercial, utility, interconnection, parcel, permit-detail, mixed-rights, or explicitly excluded country lanes. |
| Satellite review | Backlog | Unknown030 has 2,086 pending catalog jobs; all three priority lanes total 4,431 complete and 313 no-scene jobs. The 43 selected historical-v1 reviews (12 retain and 31 reject) and the separate 58 current active-lane v2 machine-proposal rows across 40 AOIs do not exhaust candidate-level manual verification. |
| Site resolution | Partial | Links remain advisory; England, Ireland, NSW, Netherlands, New Zealand, and France observations and imagery labels are not cross-source deduplicated, no merges are accepted, and unique sites remain `null`. |
| Type, power, and energy | Partial | Type, operating model, typed capacity, power, annual energy, PUE, and workload remain sparse and source-scoped. France preserves projections and distinct grid, backup, and support metrics; NSW retains 10 untyped statements; Netherlands and New Zealand promote no typed facility metrics. |

This is evidence of a reproducible current baseline, not a claim that the Atlas is already equal or
superior to a commercial report.

## Deterministic reproduction

The definition pins every primary manifest, assessment, calibration, pilot, and metric document by
exact byte count and SHA-256. Manifest bindings and sidecars are checked before the ledger is
reconstructed byte-for-byte without network access. Focused tests also independently bind the
manifest-listed England and NSW JSONL releases without broadening the ledger parser.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 datacenter_atlas/scripts/build_current_coverage_ledger.py \
  --definition datacenter_atlas/sources/current-coverage-2026-07-19-v9.json \
  --output datacenter_atlas/current_coverage_ledgers/2026-07-19-v9 \
  --validate-only
```

The frozen v9 directory is mode `0555` and its files are `0444`. Its current hashes are:

- definition: `b4686cfe1721bca36775bcf05cc9e232b60e6850848cf2a047cb5e096486b365`;
- ledger: `9c74baec74eab5b7a7f79eb6dc29d77f0071d99f0b3b67ff88fe3a337b0f32c9`;
- bundle manifest: `b96e641ec861f1db20b312dd281fb9d6d5327236c8fef1389fd00f6144e419b9`;
- bundle sidecar: `695afea6970b431e7f1a3e1afa815e84e2755447d92a51981cadf0f29e27b252`;
- construction-master v13 definition/manifest: `6058791e9027793a9767eb27a70160514db11ffcf5e5e0577b8b1d9a3a921b07` / `d5088f9b319362a248abcd0d0e9a8902c288eddedc29cfedbe1e4e2ef9bd5ad0`;
- construction-map v13 definition/manifest: `56e7edc827a30763e246bdde61724a024a7cd4482e42765f8ebf89ce15b23483` / `0a07c6b295589c22224bf9ba274ccfd8fa83d401d40fc046b9267e8c3647bb49`;
- open-seed v32 definition/manifest: `97662af3ab781b5505de1d436a06cac55002fc332cef641a7f61469486c0f150` / `85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c`;
- public federation v11 definition/manifest: `e88c5f46b19401ed12af93a5869d29af5392da6f4810fd9652279652a9d6e03c` / `9d5d98bf1a7cef9a4dd5dc1637e8f7c4d896230640b7a342d4055a4c39802be4`;
- public coverage-audit v12 definition/manifest: `1f6560b2ad5d109c3c3d544829bc87bcb77e0141b2e3cb5bc59230bf85885f7f` / `5f9b13e4f2ee7cfe28a8c3dee9756f1ed742df1c82bdb31dfc9b0bf0ec25ab77`;
- candidate-fusion v13 manifest: `12fc7517e5fdb4e00c2a7e59c069d868801ac87ecbc8c0237433b65e51ab9cc9`;
- current cumulative Unknown030 batch manifest: `18d154cfa6a445be775d6e7c35aea4d9c89d6fd84d57054ef00e541a5f56d053`;
- England planning manifest: `774c51894a2a46cbb10459cc1ebd777059c5bdab425599bfc48b6dd9d248676c`;
- NSW major-projects manifest: `650c9b6e194fea0dbe1ce28ecba0cb8f114b8ec7d6571a0ee1f31c41f0d660f2`;
- Netherlands KOOP manifest: `2fc151a0088f4d03cba8985fb45552400236518cd9022672d49280ab9d4d9cd2`;
- New Zealand Fast-track manifest: `97e9b78cc516acd48e6d3e3f80d367977bc7ae3b882820dc3e0f7e185b6cb264`;
- France IGEDD/Ae manifest: `aef3c9b21a07d436bd48eafc26fb67e9ea81dbbb827f76429f66e65708307e49`;
- satellite-calibration v4 manifest: `a3b153c97286a9c93a2b654f427fabdb1bffafc950dc0e6a6ba5c1bdf9ff1c41`;
- rejected algorithm-v2 identity-blind rereview audit v4 manifest: `be0e7042eac7a54697ff526400537fe66211dbbdf7d5a505c541a3a6fc4b590d`;
- independently accepted identity-blind rereview audit v5 manifest: `dff606bfbd4015c51d24387d4b9a73a48b236895d745b7343aacfe46a5ef57e7`;
- Microsoft buildings manifest: `4097ff7fc71d756544b4123efee660de3e7c2e32966bd20b27597f7ab22e3892`.

The v4 definition/ledger/manifest hashes remain
`dd02b5ef0bc1c4d62fb8fa3216421a55d28c9db632b2eb2c7b3e5860776cc2e5`,
`c9215177aec87aa43e8088a12105084b6008d04134b78e5ed7118f7e236f2651`, and
`0d416245a2cbd5ccd004d4bad9da171a2788af2d48149c1ab6c45dbfbc2299b7`. The v3
definition/ledger/manifest hashes remain
`839ca30072dd6df7c22de1ccfbe1153280f32fcf11e01c328f1d1c1d25c95583`,
`fddf5159029e2d64fc45c1ce884ef48cbdd26835fff3d386a6b7ea18418837ff`, and
`5f7ec30a509efbef83b1cb7d0fe18e5635429f2c0050b33f02c4241c124a3d0b`. The v2
definition/ledger/manifest hashes remain
`edf1eda55eee7ea9dd25d68b67764cbcf92dc35faaa1cd545d5dcf875e33c55b`,
`f459329472044ff78a09b20573e04c023304d2a0d0c74d7c0285294ed2edb736`, and
`77b38adc5cccbf595ba8e90e3b4f4028fdac06c6d964d193f5d55dfe88bd5694`. The v1
definition/ledger/manifest hashes remain
`b487427943fe744c3e186ecd4132fee753327b6cbd9b5552c2f6695f6ee295bd`,
`e832a7c672cba1ccfa0b5e86b97e05a26c97acd7d50922b4c40efd69ddc4348c`, and
`27eef1ad145e7b2c43a93b28a93240d74538362018158677f422e281285dd0aa`.
