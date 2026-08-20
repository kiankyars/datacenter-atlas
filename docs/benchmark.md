# SemiAnalysis parity benchmark

Snapshot date: 2026-07-21.

SemiAnalysis vendor-reports more than 5,000 facilities and says it tracks their deployments in its
institutional [AI Datacenter Model](https://newsletter.semianalysis.com/p/datacenter-model)
(accessed 2026-07-19). Its stated evidence inputs include property records, permits, power usage,
FOIA requests, satellite imagery, and computer vision. The current
[institutional product summary](https://semianalysis.com/models-research/) (accessed 2026-07-19)
describes the same greater-than-5,000-facility surface. That is a product-scale claim, not an
independently verified facility count, accuracy result, or assurance that every field is populated
for every facility. Publicly described outputs include:

- building, site, cluster, city, region, company, and geography views;
- historical, current, and forecast critical IT capacity;
- PUE, utility power, annual consumption, grid tagging, and generation mix;
- hyperscaler self-build versus leased capacity and accelerator deployment;
- capex, equipment suppliers, tariffs, carbon, power scenarios, and AI-cloud TCO.

The separate public [SemiAnalysis Energy Model](https://semianalysis.com/energy-model/) (accessed
2026-07-19) adds U.S. utility-level load forecasts adjusted for PUE and reserves, ESA/LOA tracking,
inventories of
existing and planned generation, transmission-project tracking, and supply-demand-gap analysis.
The Datacenter Model page states a 2023-2030 data horizon and one year of quarterly updates.

In a [2026-06-18 methodology article](https://newsletter.semianalysis.com/p/stop-saying-half-of-2026-us-datacenter),
SemiAnalysis also says it reviews each site dozens of times per year, trained its Vision Model on
hundreds of thousands of satellite images, and excludes low-probability projects from delivery
timelines. These remain vendor methodology and performance assertions, not published benchmark
results. The older statement that CNN work would expand tracking toward every data center in every
country describes an objective, not achieved global completeness.

These are vendor-described product features, not independently verified accuracy results. Atlas
uses them as the minimum feature benchmark. No licensed common row-level benchmark is currently
available, so coverage, field, freshness, and accuracy parity cannot be measured.

## Evaluation protocol

1. Acquire a licensed SemiAnalysis snapshot or arrange a blind third-party comparison. Never scrape
   the institutional product.
2. Freeze an evaluation date and a stratified sample across geography, operator, size, service model,
   climate, and lifecycle stage.
3. Normalize both datasets to common campus, facility, building, and phase IDs. Report both campus-
   and building-level scores so splitting strategy cannot inflate recall.
4. Adjudicate ground truth from authoritative documents and imagery not used by either system where
   possible.
5. Score coverage, freshness, accuracy, calibration, and lineage. Publish missingness and disputed
   cases rather than resolving every disagreement in our favor.

## Required scorecard

| Dimension | Metric | Initial parity target |
| --- | --- | --- |
| Facility registry | Deduplicated campus/facility/building/phase precision and recall | Match or exceed on a licensed blind common sample; the vendor-reported >5,000 count is context, not truth |
| Construction discovery | Recall above the declared 10 MW / 5,000 m² floor | At least equal on the licensed common sample; internal gate ≥90% |
| False positives | Confirmed-site precision | ≥95% |
| Freshness | Median/P90 days from first visible or official construction event | Lower is better; event-driven ingest plus quarterly full audit |
| Entity resolution | Duplicate campuses and incorrect phase splits | <1% |
| Lifecycle | Macro-F1 and event-date error | ≥0.80 and median ≤30 days |
| Power | Absolute log error, bias, and interval coverage | Match or improve Epoch's public 80%-within-1.4× reference on a larger blind set |
| Provenance | Published fields with claim-level lineage | 100% |
| Uncertainty | Brier score/ECE and empirical interval coverage | 80% intervals cover 75–85% |
| Global balance | Recall and observation age by country/region | No region hidden behind a global average |
| Energy system | Utility-load forecast error, ESA/LOA coverage, generation/transmission inventory precision, firm-capacity error, and supply-gap error | Match or exceed on a licensed or blind U.S. utility sample |
| Completeness honesty | Random-cell audit and capture-recapture unseen-site interval | Required in every census release |

## Feature parity ladder

1. **Registry parity:** more than 5,000 deduplicated facilities with status, roles, geometry, and
   evidence. Headline row count alone does not pass.
2. **Construction parity:** phase-level history, dated imagery observations, and forecast versus
   observed milestones.
3. **Power parity:** separate grid, facility, critical IT, generation, PUE, load factor, and annual
   energy distributions.
4. **Compute parity:** accelerator deployments and workload inference with source-specific
   uncertainty.
5. **Economic parity:** capex, equipment, tariffs, carbon, grid constraints, and TCO.
6. **Energy-system parity:** utility-level load and reserves, ESA/LOA state, generator, storage,
   onsite-energy and transmission inventories, firm capacity, and supply-demand gaps.

The public product may be superior before all six feature steps if it demonstrates materially better
recall, freshness, accuracy, reproducibility, or uncertainty on the common benchmark. It may not
claim superiority solely because it exposes more speculative rows.

## Current evidence inventory (2026-08-18 audit)

The newest artifact in each lane is not a single same-date publication chain. Open-seed v97,
federation v38, exact identity v14, and timeline v11 postdate the inputs pinned by coverage,
construction-master, and construction-map v31. Cross-version counts are not additive.

[Open-seed v97](../releases/2026-07-22-open-seed-v97/) contains 1,053 source-scoped entity rows,
693 evidence rows, 570 typed capacity observations, and 531 construction-pipeline rows. Federation
[v38](../federated_indexes/2026-07-22-public-open-v38/) indexes 16,478 source-scoped rows: 10,348
non-review and 6,130 review-only. Neither count is a unique-facility denominator.

[Exact-identity v14](../exact_identity_decisions/2026-07-22-public-open-v14/) reduces the 10,348
eligible non-review occurrences to 8,616 exact same-kind source-record components. It preserves
2,517 canonical topology links and leaves 100,541 candidate references unresolved. Unique physical
sites and both site-count bounds remain `null`.

[Timeline v11](../construction_timelines/2026-07-22-public-open-v11/) publishes 607 raw dated
lifecycle observations for 583 source-scoped entities. It assumes no persistence, interpolation, or
current construction state; every current-status classification remains unknown. [Coverage v31](../audits/2026-07-21-public-open-coverage-v31/)
reports 979 coverage groups and 4,582 open gaps, based on its older pinned chain.

The accepted construction-master v31 manifest declares 109,381 observation rows: 589 Tier A, 6,298
Tier B, and 102,494 Tier C. The map v31 manifest declares 109,008 mapped observation rows. Those are
observations, not sites, and the locally present large payloads are ignored by Git; a clean clone
contains their manifests but is not a hydrated publication workspace. Coverage-ledger v26 likewise
remains a scoped artifact inventory rather than a site total.

The latest satellite continuation, Unknown038, reports 4,493 catalog pairs completed, 307 no-scene
outcomes, 1,936 pending jobs, and zero failures. Its post-freeze state is `incomplete` and its mode is
`catalog_only`: no imagery assets were downloaded, no computer vision or change analysis ran, and no
Atlas identity, lifecycle, operating-status, type, capacity, power, energy, PUE, workload, map, or
unique-site claim was created.

A licensed row-level benchmark, shared ontology, adjudicated blind sample, and the scorecard's
accuracy/calibration results remain absent. Current Atlas row counts and SemiAnalysis's
vendor-reported facility count are not comparable denominators. No parity or superiority claim is
supported.

## Historical evidence inventory (2026-07-21)

The remainder of this section preserves the prior v73/v33/v9/v6/v29/v23 checkpoint as historical
evidence. It is not the current workspace inventory.

The frozen [public/open construction master v29](../construction_master/2026-07-21-public-open-v29/)
contains 109,332 observation rows: 540 Tier A, 6,298 Tier B, and 102,494 Tier C. This is not a count
of facilities. Construction arithmetic includes only source-supported Tier-A observations. The 412
rows normalized as `under_construction` are dated last-observed facts; they do not establish that
construction remains current. Tier B contains official-process and fuzzy review leads. Tier C
contains 102,451 structural footprint candidates and 43 selected analyst imagery reviews. Neither
Tier B nor Tier C enters construction arithmetic, and unique physical sites remain `null`.

[Open-seed v73](../releases/2026-07-21-open-seed-v73/) contributes 818 source-scoped entity rows,
split into 431 campus and 387 project observations, with 420 construction-pipeline rows and 534
typed capacity observations. Its typed rows comprise 267 `critical_it_mw`, 133
`gross_facility_mw`, 23 `grid_connection_mw`, four `generation_nameplate_mw`, 101
`annual_energy_mwh`, and six `pue` observations. These are typed source observations with distinct
stages and scopes, not additive site, load, or energy totals. Only 192 seed rows have coordinates.
The seed sets `current_status_inferred` to `false`; all 462 lifecycle-bearing entities have unknown
current status in the accepted timeline.

[Federation v33](../federated_indexes/2026-07-21-public-open-v33/) and
[coverage audit v29](../audits/2026-07-21-public-open-coverage-v29/) record:

- 16,243 source-scoped rows: 10,113 non-review and 6,130 review-only;
- 6,670 construction-pipeline records: 540 non-review and 6,130 review-only candidates;
- 1,320 capacity observations and 13,533 evidence records; and
- 847 release/source/country coverage groups with 4,103 deterministic open gaps.

Coverage v29 reports 412 non-review rows whose last-observed value is `under_construction` and 18
review-only under-construction leads. Both are observation counts, not current-status or site counts.
Its explicit comparison classifies SemiAnalysis's vendor-reported greater-than-5,000-facility claim
as not comparable to Atlas source-scoped rows. Federation v32 is a retained, rejected
partial-publication incident and contributes no accepted row.

[Exact-identity decisions v9](../exact_identity_decisions/2026-07-21-public-open-v9/) reduces the
10,113 eligible non-review occurrences to 8,381 exact source-record components and preserves 2,396
explicit topology links. It leaves 100,539 candidate references unresolved; unique physical sites
and both physical-site bounds remain `null`.

[Construction timeline v6](../construction_timelines/2026-07-21-public-open-v6/) publishes 479 raw
dated lifecycle observations for 462 source-scoped entities. It has 17 multi-observation entities,
13 with a status change, but classifies current status as unknown for all 462. It does not assume
that the latest observation persisted, interpolate missing milestones, or promote permits,
forecasts, satellite imagery, or computer-vision review to physical construction.

None of these seed, federation, audit, identity, timeline, master, or review totals is a
unique-facility count.

The official-process lanes remain source observations, not resolved facilities. Ireland emits 114
rows and 32 advisory relationship groups; NSW emits 22 rows; Netherlands emits 13 direct rows;
New Zealand emits three rows; and France emits three direct project opinions plus one related grid
follow-up. Their process state, source grouping, description, coordinate, and metric fields do not
establish a cross-source identity, physical lifecycle, or unique site.

Candidate-fusion v13 retains 14,324 review-ordering overlays from the 102,451-row structural
shortlist and pins 43 historical algorithm-v1 analyst report/review pairs. Analysts retained 12 visible-change AOIs for
follow-up and rejected 31 masks for site promotion. The priority tiers contain 28 candidates
overlapping retained-review AOIs, 1,037 distinct-source-root opportunities, and 13,259 shared-root
or queue opportunities. One analyst AOI can overlap several candidates.

The current bounded [v73 satellite queue](../satellite_review_queues/2026-07-21-open-seed-v73/)
contains 192 coordinate-bearing seed jobs: 100 active-construction, 29 operational, five
proposed-pipeline, and 58 unknown-priority. Another 626 seed entities lacked coordinates and were
skipped. It adds exactly the newly located SC2 project, S4 project, and S4 campus records to v71
and removes none. The completed
[explicit catalog tranche](../satellite_review_runs/2026-07-21-open-seed-v71-active-explicit-final-v1/)
was sampled from the predecessor v71 queue: it represented all 98 v71 active jobs, selected 11,
completed all 11 with no failure or no-scene result, and left the other 87 pending. The corresponding
historical `2026-07-21-open-seed-v71-active-explicit-001` visible-change run also completed 11 of 11,
but that intermediate payload is not distributed in the public clean clone. Its
[identity-blind analyst review](../satellite_change_reviews/2026-07-21-open-seed-v71-active-explicit-11-review-v1/)
retained seven visual results for manual follow-up and rejected four for site promotion. These are
review dispositions, not seven construction sites: no Atlas row, identity, operator, lifecycle,
current-status, type, capacity, power, energy, PUE, workload, construction arithmetic, or
unique-site claim was created.

The earlier global catalog accounting across active-001, proposed-001, and cumulative Unknown034
contains 4,478 completed scene pairs, 316 no-scene outcomes, zero failures, and 2,036 pending jobs
across 6,830 queue rows. Unknown034 remains an intentionally incomplete catalog-only checkpoint; it
ran no computer vision or change analysis and inferred no identity, lifecycle, operating status, or
power. Fusion separately records 5,352 completed, 295 unavailable, and 18,772 pending candidate-AOI
catalog links from its frozen Unknown015 lineage; those are historical link counts, not additional
jobs. Catalog availability, visible change, and analyst review create no automatic identity or
lifecycle label. Calibration v4 audits the same selected 43 historical-v1 reviews but has no random
sample, recall denominator, generalized accuracy result, or production threshold. It does not
calibrate the current v2 processor. The later independently accepted identity-blind v5 rereview
covers 36 current-v2 comparisons and leaves seven multi-tile rows blocked; its 30-of-35 binary
agreement is descriptive, not an accuracy, recall, truth, or production-threshold result.

The separate frozen change-analysis v2 checkpoints publish 58 current machine-proposal rows across
40 exact active-lane AOIs. Two qualification rows share one byte-identical Virginia comparison,
other entity rows and AOIs also duplicate or overlap, and neither count is a site total. Visual
inspection created no analyst-decision artifact. The proposals remain outside public federation
v33, master v29, timeline v6, identity v9, candidate-fusion v13, historical calibration, lifecycle
arithmetic, and every capacity, power, and energy count. The coverage ledger inventories their
artifacts without importing the proposal rows as construction or site claims.

The Microsoft building-footprint bundle inventories 30,344 location/quadkey rows across 225
locations. Its four-shard pilot retains 671 footprint review rows near four construction priors.
Atlas assigns no identities, statuses, types, or metrics to those footprints. Spain BOE, Italy
MASE, Brazil PNCP, Germany UVP, Finland LVV, Denmark Plandata, Poland GDOŚ/SIOS/Ekoportal,
South Korea EIASS/NIER, Japan MOE, Malaysia KPKT, Singapore BCA, Singapore URA, India PARIVESH,
Thailand ONEP, Canada IAAC, Chile SEA, and Australia EPBC remain separate bounded assessments under
their frozen import, record-unit, access, and rights contracts. Their publication, process,
certification, or search counts do not automatically enter the construction master. Singapore BCA's
complete 4,793-row voluntary-certification snapshot
produces 101 data-centre review observations and four provisional-letter leads, but no physical
lifecycle, project, site, power, energy, PUE, operator, type, or coordinate fact. Malaysia KPKT and
Singapore URA and India PARIVESH are zero-row metadata-only assessments with unobserved source
counts and observed coverage dates left null. India's 2006 lower bound belongs only to an
unexecuted future query plan. Thailand ONEP is also zero-row: one of its four controlled GETs
captured a catalogue-linked JSON response that advertised 13,793 records over 138 pages but
returned only 94 page-1 rows, including three
future-dated approvals, so the assessment stopped without pagination or candidate derivation.
Loudoun, Prince William, Virginia DEQ, Cleanview, and PJM likewise remain metadata, aggregate,
local-review, or zero-row assessments.

[Construction map v29](../construction_maps/2026-07-21-public-open-v29/) indexes all 109,332 master
observations, maps 108,998, leaves 334 unmapped, and selects 6,504 coordinate-bearing Tier A+B
observations by default. Its mapped tiers are A 224, B 6,280, and C 102,494. Map points preserve
observation units and do not resolve unique sites.

[Coverage ledger v23](../current_coverage_ledgers/2026-07-21-v23/) closes 50 artifact contracts.
Forty v22 entries remain byte-identical, seven are one-for-one successors for seed v73, timeline v6,
federation v33, identity v9, coverage v29, master v29, and map v29, and three add the bounded v71
satellite queue, catalog, and blind-review contracts. The ledger preserves each artifact's scope and
does not make cross-artifact counts additive.

A licensed row-level benchmark, common ontology, adjudicated blind sample, and the scorecard's
accuracy and calibration results remain absent. Current row counts and review volume cannot
establish registry, construction, power, compute, economic, or energy-system parity. Neither
SemiAnalysis's vendor-reported greater-than-5,000 facilities nor Atlas's 109,332 master observation
rows is a valid comparative denominator without a licensed common ontology and adjudicated
row-level sample. No SemiAnalysis parity or superiority claim is supported.
