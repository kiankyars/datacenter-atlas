# Data Center Atlas

This directory is a self-contained, Python 3.11+ standard-library foundation for a provenance-first
global data-centre construction registry. Its design keeps source observations separate from
derived current state: a facility status, workload classification, or power estimate cannot exist
without evidence and an as-of date.

The canonical hierarchy distinguishes campuses, facilities, buildings, and development projects.
Operating model and workload are independent classifications. Power observations preserve whether a
number means grid connection, gross facility load, critical IT load, generation nameplate, annual
energy, or PUE; estimates carry low/base/high values, method, confidence, and evidence.

## Current workspace state (audited 2026-09-06)

The current user-facing construction product is the
[Verified Construction Core v0.17 preview](verified_construction_core/2026-08-20-preview-v0.17/),
with its [selection contract and final gates](docs/verified_construction_core.md). It contains 103
recently observed projects grouped into 100 source-scoped physical sites across 40 countries, of
which 70 are outside the United States, with 252 closed-set evidence rows. Five project rows carry
official parcel or surveyed geometry; 98 use explicitly scoped locators. The source-selection
ledger attributes 97 selected projects and 434 nonselected rows to the frozen 531-row v97 pipeline.
Six projects are explicitly post-v97 portable additions, bringing the artifact cohort to 103
without presenting them as v97 rows. The v0.17 delta adds 20 distinct sites: 16 reviewed v97
promotions and four post-v97 additions, including seven sites that expand the cohort to China,
Czechia, Denmark, Nepal, New Zealand, Niger, and Romania. Every v0.17 geometry is a project or
campus locator with `official_boundary=false`; geometry creates no lifecycle, footprint, capacity,
role, or workload claim. The cohort lifecycle cutoff remains 2026-08-20, while the v0.17 geometry
and identity review was accepted on 2026-09-06. The manifest and selection report record both
clocks separately.

The site-count, country-diversity, non-US share, maximum-country-share, and clean-clone gates now
pass. The artifact nevertheless remains a preview: imagery outcomes cover only 10 of 103 projects,
the required 20-row blind review has not begun, and `publishable_as_final=false`. It is not the
promised final release or a claim of SemiAnalysis parity. The
[v0.16 preview](verified_construction_core/2026-08-20-preview-v0.16/),
[v0.15 preview](verified_construction_core/2026-08-20-preview-v0.15/),
[v0.14 preview](verified_construction_core/2026-08-20-preview-v0.14/),
[v0.13 preview](verified_construction_core/2026-08-20-preview-v0.13/),
[v0.12 preview](verified_construction_core/2026-08-20-preview-v0.12/),
[v0.11 preview](verified_construction_core/2026-08-20-preview-v0.11/),
[v0.10 preview](verified_construction_core/2026-08-20-preview-v0.10/),
[v0.9 preview](verified_construction_core/2026-08-20-preview-v0.9/),
[v0.8 preview](verified_construction_core/2026-08-20-preview-v0.8/),
[v0.7 preview](verified_construction_core/2026-08-20-preview-v0.7/),
[v0.6 preview](verified_construction_core/2026-08-20-preview-v0.6/),
[v0.5 preview](verified_construction_core/2026-08-20-preview-v0.5/),
[v0.4 preview](verified_construction_core/2026-08-20-preview-v0.4/),
[v0.3 preview](verified_construction_core/2026-08-20-preview-v0.3/),
[v0.2 preview](verified_construction_core/2026-08-20-preview-v0.2/) and
[v0.1 preview](verified_construction_core/2026-08-19-preview-v0.1/) remain byte-frozen for audit,
not as datasets to add to v0.17.

The active [200-site expansion](docs/expansion_200.md), begun on 2026-09-08, targets another 100
distinct physical sites under the same evidence standards. Candidate research is not included in
the published 100-site count above. The separately labelled
[twelfth reviewed draft](verified_construction_core/2026-08-20-v0.18-draft-twelfth-reviewed/README.md)
contains 153 sites and is reproducible with `scripts/build_expansion_200_draft.py --batch twelfth-reviewed`.
This is 53 of the requested 100 additions. All earlier checkpoints remain frozen; this checkpoint
preserves every preceding project, site and evidence row, including the documented Helios correction.

All eight inherited workload observations are machine-labelled `intended`, not operational. Nine
published operator claims and two intended-customer claims carry evidence IDs and relationship
scope. The v0.17 delta adds no normalized roles, operating models, workloads, or metrics. The
inherited v0.11 row retains one project-scoped planned 10 MW grid-connection observation for IIJ
Phase 3; the optional 25 MW expandability ceiling is not promoted as installed, contracted,
current, or additive capacity.

The latest fully present source bundle is
[open-seed v97](releases/2026-07-22-open-seed-v97/). It contains 1,053 source-scoped entity rows
(545 campuses and 508 projects), 693 evidence rows, 570 typed capacity observations, 531
construction-pipeline rows, and 432 construction-source signals. These remain observations, not a
deduplicated physical-site count, and `current_status_inferred` remains `false`.

The newest artifact in each downstream lane is listed below. These versions are not one coherent
same-date chain: coverage/master/map v31 pin earlier seed, federation, identity, and timeline inputs
than v97/v38/v14/v11. Counts from separate lanes or versions must not be added.

| Lane | Latest artifact | Current local hydration |
| --- | --- | --- |
| Verified construction preview | [v0.17](verified_construction_core/2026-08-20-preview-v0.17/) | 138 portable source and bridge inputs are manifest-bound; the generated preview remains a non-final artifact |
| Source release | [open-seed v97](releases/2026-07-22-open-seed-v97/) | All 13 manifest-declared payload files present |
| Federation | [v38](federated_indexes/2026-07-22-public-open-v38/) | Federated index present |
| Exact identity | [v14](exact_identity_decisions/2026-07-22-public-open-v14/) | All seven declared payload files present |
| Timeline | [v11](construction_timelines/2026-07-22-public-open-v11/) | All five declared payload files present |
| Coverage audit | [v31](audits/2026-07-21-public-open-coverage-v31/) | All four declared payload files present |
| Construction master | [v31](construction_master/2026-07-21-public-open-v31/) | All five declared payload files present locally |
| Construction map | [v31](construction_maps/2026-07-21-public-open-v31/) | All five declared payload files present locally |
| Coverage ledger | [v26](current_coverage_ledgers/2026-07-21-v26/) | Declared ledger payload present locally |

Git versions the code, definitions, documentation, tests, and small provenance manifests, while
large generated payloads are ignored. A clean clone therefore supports the CLI and corpus-free CI
tier, but it does not promise a hydrated publication workspace. Ignored payloads are ordinary local
files and may be copied with normal filesystem tools; historical recovery records are not required
to install or test the project.

The latest exact-identity release indexes 16,478 source-scoped records and reduces 10,348 eligible
non-review occurrences to 8,616 exact same-kind components. It leaves 100,541 candidate references
unresolved; unique physical sites and both physical-site bounds remain `null`. Timeline v11 contains
607 raw lifecycle observations for 583 source-scoped entities and classifies every current status as
unknown. Coverage v31 records 979 coverage groups and 4,582 open gaps.

The latest accepted satellite continuation, Unknown038, reports 4,493 completed jobs, 307 no-scene
outcomes, 1,936 pending jobs, and zero failures. Its post-freeze validation state is `incomplete` and
its mode is `catalog_only`: it downloaded no imagery assets, ran no computer vision or change
analysis, and created no Atlas identity, lifecycle, type, capacity, power, energy, PUE, workload,
map, or unique-site claim.

No public v32 master/map/coverage publication is present. Global coverage remains partial,
last-observed status is not current status, and cross-source resolution is not a site census. No
licensed common row-level benchmark is available, so Atlas supports neither SemiAnalysis parity nor
superiority. Older release descriptions below are retained as historical checkpoints.

## Quick start

From this directory:

```sh
python3 -m datacenter_atlas init-db --db atlas.sqlite
python3 -m datacenter_atlas import-osm \
  --db atlas.sqlite \
  --input tests/fixtures/osm_minimal.json \
  --retrieved-at 2026-07-17T12:00:00Z
python3 -m datacenter_atlas import-curated \
  --db atlas.sqlite \
  --input sources/curated-official-2026-07-17.json \
  --retrieved-at 2026-07-18T01:44:06Z
python3 -m datacenter_atlas validate --db atlas.sqlite
python3 -m datacenter_atlas summary --db atlas.sqlite
python3 -m datacenter_atlas export-geojson --db atlas.sqlite --output atlas.geojson
python3 -m datacenter_atlas export-release \
  --db atlas.sqlite \
  --output-dir release \
  --as-of 2026-07-17 \
  --recorded-at 2026-07-18T00:59:24Z
python3 web/generate_atlas.py release/atlas.geojson release/atlas.html
```

The checked multi-source seed is rebuilt without network access by `scripts/build_open_seed.py`;
the script imports all matching strict curated records in stable filename order, validates the
temporary database, refuses to overwrite an existing output, and writes a provisional hashed
bundle. `scripts/validate_open_seed_release.py` then reconstructs every distributed byte from the
pinned inputs before the release is frozen read-only.

The checked [2026-07-18 global open snapshot](releases/2026-07-18-global-open-v3/) is the current
Planet-scale release. It contains 9,295 source-scoped entities, including 4,836 exact records from
the official 2026-07-13 OpenStreetMap Planet, 1,474 PNNL/IM3 candidates, 189 Wikidata candidates,
and 382 UVA DC-SENSE facilities. The 120 active/pre-construction **entity rows** are explicit source
claims: 99 `under_construction` and 21 `proposed`, derived from **61 distinct lifecycle
evidence/source observations**. `construction_source_signals.csv` groups the entity rows by
`status_evidence_id` while preserving every affected entity ID, kind, and stable key. This is an
evidence-level accounting view, not cross-source deduplication or a count of 61 unique physical
sites. The snapshot remains a discovery layer rather than a complete construction census or a
SemiAnalysis parity claim. `manifest.json` binds every distributed file, including the full SQLite
database and map, to its byte count and SHA-256.

The frozen open-seed v2 strict curated inputs added four Meta projects that the company's April 28,
2026 fleet update explicitly described as under construction: Richland Parish, Lebanon, El Paso,
and Tulsa. All four share one evidence observation, use approximate named-locality centroids, and
import no typed capacity or energy from the page's unscoped GW wording. They remain outside the
earlier frozen global snapshot but are preserved in the later accepted open-seed and construction
master/map releases.

A bounded [EdgeMode/SEC EDGAR assessment](docs/edgemode.md) adds nine publication-eligible,
review-only developer leads from official filings: eight named project identities and one
unresolved Palma land label. The direct EdgeMode website lane is blocked because no reuse license
or facility API was found. The SEC-derived leads have no verified construction status, coordinates,
typed current MW, annual energy, PUE, or unique-site count. Conflicting 2,850 MW named-Spain and
4,350 MW Spain-aggregate statements remain unreconciled rather than being forced into site
capacity.

The [EPA ECHO/FRS assessment](docs/epa_echo_frs.md) records one bounded NAICS 518210 query with 928
time-bounded matches and retains four explicit-name rows as local review leads only. It does not
claim U.S. completeness, construction verification, typed capacity or energy, coordinates, or a
unique-site count. The Data.gov CC0 marker is kept scoped to the named FRS Facility Interests
dataset; until exact field-level lineage to that download is checkpointed, none of the four rows is
publication eligible or mergeable.

Atlas keeps rights- or scope-restricted assessments outside the publishable row ledger.
[Loudoun County](docs/loudoun_data_center.md) exposes 139 existing and 85 pipeline parcel records,
but unresolved layer rights limit the bundle to metadata and aggregates. [Virginia DEQ](docs/virginia_deq_air_permits.md)
contributes a local-review snapshot of 198 issued-permit actions and one under-review application.
All Rights Reserved terms block row publication, and the records verify no construction. The
[Cleanview](docs/cleanview.md), [Prince William County](docs/pwc_build_out.md), and
[PJM](docs/pjm_large_load.md) assessments emit zero facility rows. Cleanview requires an approved
API key and product-integration license, Prince William's three entity-level counts cannot be
summed or redistributed under the retrieved terms, and PJM's 42-document corpus contains grid and
forecast evidence without canonical facility records. The bounded Spain, Italy, Brazil, Germany,
Finland, Denmark, Poland, South Korea, Japan, Malaysia, Singapore BCA, Singapore URA, India, Thailand, Canada, Chile, and Australia source assessments
remain separate under their explicit import, record-unit, access, and rights contracts; see the
[source registry](docs/source_registry.md). Singapore BCA publishes 4,793 voluntary-certification
observations and a closed 101-observation data-centre review union, but no construction or
unique-site facts. Malaysia, Singapore URA, and India publish zero source rows; their unexecuted
search plans do not establish observed source coverage. Thailand also publishes zero rows: the one
catalogue-linked Smart EIA snapshot response advertised 13,793 records across 138 pages but returned only
94 rows, including three future-dated approvals, so the lane failed closed without pagination.

The bounded Denmark Plandata.dk WFS assessment completes 27 exact local-plan name queries and
retains five adopted-layer planning observations from five memberships. Proposal and cancelled
matches are zero, but the result is not national data-centre completeness. Adoption is not
construction; documents and PDFs were not requested; identity, operator, type, physical status,
power, IT load, PUE, energy, workload, and unique sites remain unknown. The clean capture made 35
paced, hash-bound requests. Full task accounting is 67 direct local GETs, including 32 disclosed
discarded probes that are neither paced evidence nor coverage results.

The Poland GDOŚ/SIOS/Ekoportal lane is a frozen zero-row access and rights assessment, not a
zero-result search. Its 10/40 paced direct attempts include no result, export, detail, or document
request. SIOS robots disallows the search surface; result-level reuse, exact matching, pagination,
page size, and stable sorting are unresolved; GDOŚ/RDOŚ routing is not all-authority national
coverage; and the statutory national EIA database is blocked outside Poland. All result, project,
site, lifecycle, and metric counts therefore remain unknown, and no construction import is allowed.

The South Korea EIASS/NIER lane is also frozen at zero rows. Two current, attribution-licensed
machine-readable project-list APIs are documented, but both require a Public Data Portal service
key. The API-host robots request returned HTTP 500, and page-size bounds, stable ordering, snapshot
semantics, and exact project-name matching are undocumented. No Korean or English data-centre
literal was submitted. EIA discussion status is review-only administrative evidence, not physical
construction, and every project, site, lifecycle, type, capacity, PUE, and energy count remains
unknown.

The [Japan MOE data-centre decarbonization casebook lane](docs/japan_moe_casebook.md) is a frozen,
review-only auxiliary release. Its May 2026 casebook has nine overview rows and eight detail pages:
seven reconcile, two are overview-only, and one is detail-only, producing ten case observations—not
ten physical sites. The release also preserves 24 page-scoped renewable-generation, energy-savings,
renewable-share, and CO2-reduction metrics plus six program observations. Program categories and
reported effects do not establish physical identity, lifecycle, type, IT load, power capacity, PUE,
or annual electricity consumption. EcoKaku's bare MWh values are not annualized, and the printed
Kanden/IIJ `1.1 MWh/year` value is retained with its internal-consistency warning. Construction-master,
construction-map, and current-coverage-ledger imports are zero.

The retained `global-open-v1` directory predates canonical ISO normalization for 105 ungeocoded
source-country fallbacks. `global-open-v2` added that normalization but predates the distinct
construction-source-signal export. Use `global-open-v3`; it retains the original source tags for
audit and exposes both the 120 entity-level construction rows and their 61 lifecycle evidence
observations.

The dependency groups and `uv.lock` pin the test, imagery-test, and lint runtimes. Install the full
test environment and run pytest with:

```sh
uv sync --locked --group test --group imagery-test --python 3.12
PYTHONDONTWRITEBYTECODE=1 \
  uv run --locked --group test --group imagery-test \
  python -m pytest tests
```

The full suite also validates ignored release corpora and frozen filesystem modes, so it requires a
locally hydrated workspace. The GitHub clean-clone workflow runs the smaller standard-library core,
workspace-shim, CLI, lock, and lint checks without those ignored artifacts.

## OSM import policy

The importer accepts an offline Overpass-style JSON file; it never fetches bulk data. It imports only
elements carrying explicit data-centre tags, not elements whose names merely contain “data center.”
`construction:*`, `proposed:*`, `building=construction`, and `building=proposed` forms are interpreted
conservatively. An ordinary mapped data-centre object receives `unknown`, not `operational`, because
OSM geometry alone does not prove commissioning.

Every imported element records its canonical OpenStreetMap element URL, retrieval timestamp,
`ODbL-1.0` license, and `© OpenStreetMap contributors` attribution. Any downstream public export must
retain the attribution and comply with the Open Database License.

The separate fuzzy Planet workflow expands recall for spelling, spacing, case, semicolon-list, and
unknown-key variants. It is a review-only candidate layer, not a census: canonical 92-pair matches
are flagged and excluded from supplemental import, textual matches remain low-confidence `lead`
records, and the adapter infers no capacity, facility type, workload, or operating model. Run
`scripts/extract_osm_planet_fuzzy.py --dry-run` to inspect the 16 wildcard expressions without
starting a second Planet-scale extraction; a live run should happen only after reviewing that plan.

The checked [fuzzy review v2](releases/2026-07-18-osm-fuzzy-review-v2/) retains all 6,130
supplemental rows for audit and publishes a 555-row higher-signal shortlist. The other 5,575 rows
are mostly source/reference text or similarly weak context and remain outside the shortlist.
Neither set is a confirmed facility list; the child manifest declares `review_only`.

The exact global extraction retains node, way, and relation references from the verified
87 GiB Planet rather than relying on API sampling. Its materializer emitted all 4,836 exact matches
once, with zero missing references and zero coordinate-less matches. Seventy-nine relation polygons
assembled without error; one overlapping-ring relation remains marked unresolved without
simplification.

The separate [structural construction discovery lane](docs/osm_construction_discovery.md) scans the
same hash-verified Planet for a bounded set of explicit construction/proposal forms and foundation
objects, retaining references and checking them before publication. It materializes every raw match,
computes polygon footprint area, and emits a review-only shortlist using published size,
industrial-tag, electrical-tag, and mapped-power-context rules. Exact typed OSM identities already
in the 4,836-object data-centre layer are linked and excluded. The lane infers no data-centre
identity, status, capacity, workload, operator, power demand, or energy consumption and is never
imported into the atlas database.

The checked [2026-07-18 v3 candidate bundle](releases/2026-07-18-osm-construction-candidates-v3/)
contains 1,446,595 raw primary matches and 102,451 polygon review candidates. It preserves 126 exact
typed links to the canonical data-centre layer while excluding those identities from the shortlist.
The raw count includes source matches of every geometry type; it must not be reported as a count of
data centres or construction sites.

The frozen [Microsoft Global ML Building Footprints lane](docs/microsoft_global_ml_building_footprints.md)
inventories 30,344 unique location/quadkey rows and URLs across 225 locations. Its bounded pilot
downloads four country shards and retains 671 footprint review rows near four source-supported
construction records. Atlas treats the review rows as non-merging context and infers zero
data-centre identities, lifecycle states, types, capacities, power values, energy values, or unique
sites.

For the global lead layer, `scripts/fetch_ohsome.py` partitions an explicit WGS84 extent, fetches
serially with checkpoints and bounded retries, and adaptively subdivides oversized cells. Importing
its manifest fails closed unless every leaf shard completed and every saved hash/count verifies;
partial import requires an explicit `--allow-partial` flag and remains labeled in warnings.

`scripts/fetch_taginfo_targets.py` is the sparse query planner. It checks every equality term in the
same OSM filter, saves and hashes the exact Taginfo statistics and node/way distribution images, and
turns their occupied one-degree pixels into auditable coarse Ohsome targets. Those pixels are only
tag-presence signals, with no facility, geometry, or count claim. The targeting manifest reports
nonzero statistics with empty maps and relation occurrences, because Taginfo exposes no relation
distribution image and neither gap may be treated as covered.

```sh
python3 scripts/fetch_ohsome.py --output saved-ohsome --time 2026-06-19T09:59:00Z
python3 -m datacenter_atlas import-ohsome \
  --db atlas.sqlite \
  --input saved-ohsome \
  --retrieved-at 2026-07-18T02:00:00Z
```

The timestamp above was inside the live API's available history during the 2026-07-17 build; the
ohsome backend lagged current OSM by about four weeks. A release must record that source snapshot
date separately from its later retrieval time.

The PNNL/DOE IM3 adapter pins the published v2026.02.09 U.S. GeoPackage by URL, byte count, and
SHA-256 before opening it as SQLite. The verified artifact contains 1,479 source rows, which import
as 1,474 source-scoped candidates; five duplicate county rows are retained in candidate metadata.
The import creates 2,711 entities, including 1,237 structural facility parents needed to represent
building candidates in the atlas hierarchy. This layer is derived from OpenStreetMap and licensed
under ODbL, so it is not independent corroboration of direct OSM evidence. Every imported candidate
has `unknown` lifecycle status, and the adapter infers no project, capacity, operating-model, or
workload claim.

```sh
python3 scripts/fetch_pnnl.py --output saved-pnnl
python3 scripts/import_pnnl.py \
  --input saved-pnnl \
  --database atlas.sqlite \
  --retrieved-at 2026-07-18T00:00:00Z
```

The UVA DC-SENSE adapter pins Dataverse version 2.0 and the original-format `ModelOutput.csv`
bytes (stored locally as `ModelOutput.tab`) by byte count, MD5, and SHA-256. Its strict 161-column
import creates 382 source-scoped Virginia facilities with closed GeoJSON polygons and `unknown`
lifecycle. It adds modeled critical-IT intervals and a clearly labeled typical-day annual-energy
extrapolation; reported standard deviations are not treated as calibrated confidence intervals.
The model's `construction_year` remains descriptive metadata and never creates a project or current
construction/operational claim. Hyperscale, colocation, and enterprise labels receive only cautious
operating-model mappings; `Large Campus` is retained as a scale label, and no workload is inferred.

```sh
python3 scripts/fetch_uva.py --output saved-uva
python3 scripts/import_uva.py \
  --input saved-uva \
  --database atlas.sqlite \
  --retrieved-at 2026-07-18T18:00:00Z
```

Scrutica is available only as an **isolated, local-research discovery layer**. Its 2026-07-18 public
directory is a mixed inventory, not 4,234 data centres: 4,550 tracked records included 4,234
individually browsable facilities across 85 pages and 316 licensed-source rows present only in
aggregate counts. The pinned
directory types yield a strict default scope of 4,120 data-centre rows; 91 ambiguous `other` rows and
23 fab/packaging rows are excluded from imports and releases but preserved in the raw bundle. The
fetcher hashes every raw directory page, then checkpoints exact MCP SSE and parsed JSON with bounded
retries and at least 1.1 seconds between requests. The CLI defaults to 50 MCP attempts
per run. Resume the same output directory until complete.

```sh
python3 scripts/fetch_scrutica.py \
  --output saved-scrutica \
  --max-requests 50
python3 scripts/import_scrutica.py \
  --input saved-scrutica \
  --database scrutica.sqlite \
  --retrieved-at 2026-07-18T20:00:00Z
python3 scripts/build_scrutica_snapshot.py \
  --input saved-scrutica \
  --output-dir releases/scrutica-2026-07-18 \
  --as-of 2026-07-18 \
  --retrieved-at <timestamp-at-or-after-fetch-completion> \
  --recorded-at <same-or-later-timestamp>
```

Never point the importer at `atlas.sqlite`. Scrutica presents the directory under CC BY-SA 4.0 with
source-attributed exceptions, so its database and releases remain separate from the ODbL/CC0 open
release. A subsequent upstream-rights audit found 1,548 PeeringDB-derived rows with no recorded
permission or upstream license basis. The immutable Scrutica artifact is therefore quarantined from
redistribution in full until every upstream family has an evidenced reuse basis; its blanket label
is not treated as permission. The adapter and release builder enforce database isolation, while the
publication boundary is enforced by the current public/open federation. Only exact `ai_training`,
`colocation`, `edge`, `hpc_center`, and `hyperscale_dc` types become source-scoped facilities; scope
is never inferred from names. Records are never automatic merges or independent corroboration of
named upstream sources. Partial bundles are rejected unless `--allow-partial` is explicit and are
then labeled incomplete. See the [Scrutica isolation and provenance contract](docs/scrutica.md).

Separately licensed final releases can be made discoverable through a
[federated release index](docs/federated_release_index.md). The index references and hash-checkpoints
each child; it never copies child data files, combines licenses, merges entities, or reports unique
physical sites. Its arithmetic totals remain source-scoped.

The current publication-safe
[public/open index](federated_indexes/2026-07-19-public-open-v11/) references open-seed v32,
global-open-v3, and fuzzy-review-v2. Its 15,795 source-scoped rows split into 9,665 non-review and
6,130 review-only rows. Its 6,445 arithmetic construction-pipeline rows split into 315 non-review
records and 6,130 review-only candidates. Neither subtotal is a unique-site count;
`unique_physical_sites` remains `null`.

The current [public/open coverage audit](audits/2026-07-19-public-open-coverage-v12/) measures that
exact federation in 441 release/source/country groups and publishes a deterministic 2,411-entry
machine-readable gap registry. It reports coordinates, country resolution, lifecycle
freshness/evidence, source-declared entity kinds, capacity metric/stage/method/confidence,
annual-energy provenance, operating model, workload, and review scope. Its benchmark methodology
comparison resolves seven explicitly classified permitting-process records, including the Wisconsin
DNR environmental-review page, the Independence monthly permit report, and the Finnish municipal
permit update, while stating that they prove neither permit grant, project approval, nor physical
construction. Property records, FOIA,
satellite imagery, and computer vision remain absent from these audited children. The frozen v7
coverage artifact is rejected as a current view because it hardcoded permit evidence as absent;
its bytes remain preserved. The older
[four-layer index](federated_indexes/2026-07-18-four-layer-v2/) and
[coverage audit](audits/2026-07-18-four-layer-coverage-v1/) remain reproducible local research
artifacts with 19,625 rows, but include the quarantined Scrutica child and must not be redistributed
as current public output. See the [audit contract](docs/coverage_audit.md); the licensed
SemiAnalysis row-level comparison and parity remain pending.

The frozen [public/open construction master v13](docs/construction_master.md) combines the source
and review lanes into 109,107 observation rows: 315 Tier A, 6,298 Tier B, and 102,494 Tier C. Only
Tier A participates in construction arithmetic. The master has zero independently verified
construction rows and leaves the unique physical-site count `null`. Tier B includes the Ireland,
England, NSW, Netherlands, New Zealand, and France official-process review lanes without converting
their process states into physical lifecycle. The four France IGEDD rows preserve 13 explicitly
scoped metrics without unit conversion or reinterpretation. Tier C contains 102,451 structural
candidates and 43 selected historical algorithm-v1 Sentinel analyst-review observations. Relative
to v12, v13 adds exactly 11 coordinate-null project rows, all source-reported
`under_construction`. The delta adds no normalized capacity, annual energy, PUE, untyped power
statement, workload, operating model, role, geometry, or independent verification. Candidate-fusion v13 review lineage
remains pinned to Unknown010/013/015 while Unknown030 is cumulative catalog context only. Federation
v11 and permit-aware coverage audit v12 are contextual accounting inputs; their rows and arithmetic
are not copied into the master.

The frozen [construction map v13](construction_maps/2026-07-19-public-open-v13/) indexes all 109,107
master observations. It maps 108,973 rows, records 134 rows without coordinates, and opens with the
6,479 coordinate-bearing Tier A+B observations selected. Its mapped tiers are A 199, B 6,280, and
C 102,494; the v13 delta adds no mapped rows. The map preserves observation tiers and does not deduplicate physical sites. Its manifest
SHA-256 is `0a07c6b295589c22224bf9ba274ccfd8fa83d401d40fc046b9267e8c3647bb49`.

The promoted stack is hash-pinned end to end. Open-seed v32's definition/manifest SHA-256 pair is
`97662af3ab781b5505de1d436a06cac55002fc332cef641a7f61469486c0f150` /
`85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c`; federation v11's is
`e88c5f46b19401ed12af93a5869d29af5392da6f4810fd9652279652a9d6e03c` /
`9d5d98bf1a7cef9a4dd5dc1637e8f7c4d896230640b7a342d4055a4c39802be4`; coverage-audit v12's is
`1f6560b2ad5d109c3c3d544829bc87bcb77e0141b2e3cb5bc59230bf85885f7f` /
`5f9b13e4f2ee7cfe28a8c3dee9756f1ed742df1c82bdb31dfc9b0bf0ec25ab77`; and construction-master
v13's is `6058791e9027793a9767eb27a70160514db11ffcf5e5e0577b8b1d9a3a921b07` /
`d5088f9b319362a248abcd0d0e9a8902c288eddedc29cfedbe1e4e2ef9bd5ad0`. Construction-map v13's
definition/manifest pair is `56e7edc827a30763e246bdde61724a024a7cd4482e42765f8ebf89ce15b23483` /
`0a07c6b295589c22224bf9ba274ccfd8fa83d401d40fc046b9267e8c3647bb49`.
Current-coverage ledger v9 binds those products with definition, ledger, and manifest SHA-256 values
`b4686cfe1721bca36775bcf05cc9e232b60e6850848cf2a047cb5e096486b365`,
`9c74baec74eab5b7a7f79eb6dc29d77f0071d99f0b3b67ff88fe3a337b0f32c9`, and
`b96e641ec861f1db20b312dd281fb9d6d5327236c8fef1389fd00f6144e419b9`.

The redistribution-safe [within-release resolution lane](docs/within_release_resolution.md)
produces a separate immutable review bundle from the exact public inputs. It emits only typed
shared-source identities, tightly gated same-site candidates, and explicit hierarchy/part-of
candidates and no broad nearby-only rows. It retains source roots, marks generated structural
pairs, excludes the 6,130-row fuzzy review child before matching, performs no cross-release joins,
and reports neither accepted merges nor unique physical sites.

The local-research [cross-release resolution lane](docs/cross_release_resolution.md) compares the
quarantined Scrutica SQLite database with global-open-v3 in read-only mode. The atomic crosswalk
retains entity/evidence IDs, explainable spatial and semantic signals, exact child checkpoints, and
upstream source-root independence. It never
merges either child or supplies a unique-site count; the lane marks Scrutica rows derived from
OpenStreetMap as non-independent from direct OSM records. Because the link rows reproduce selected child
fields and remain subject to both child-rights boundaries, this bundle is not public output.

The checked [`scrutica-global-open-v3-v3`](cross_release_resolution/scrutica-global-open-v3-v3/)
bundle contains 62,896 advisory links: 2,737 same-site suggestions, 92 part-of suggestions, and
60,067 nearby-only links. Exactly 1,351 share a typed OpenStreetMap identity, all of them with a
shared upstream root. Only 423 same-site and 26 part-of suggestions are independent-source
opportunities; none is an adjudicated duplicate, corroboration claim, or facility confirmation.

The checked fuzzy/global-open scale pilot produced 5,740 advisory links from 6,130 fuzzy records:
4,758 links share the OpenStreetMap root and 982 are proximity opportunities against UVA or
Wikidata. None is a facility confirmation. The pilot manifest is bound by SHA-256 in its immutable
`cross_release_resolution/osm-fuzzy-global-open-v3-pilot-v2/` bundle.

## Temporal model

Observation tables use two clocks:

- `as_of_date` / `valid_to_date` describe when the claim is believed true in the world.
- `recorded_at` / `superseded_at` describe when that version existed in this database.

Evidence separately records `published_at` when known and the mandatory `retrieved_at` timestamp.
GeoJSON export accepts both `--as-of` and `--recorded-at` to reproduce historical views.

## Epoch AI open seed

The offline Epoch adapter accepts the official data ZIP and, optionally, a saved copy of the Epoch
map page. It decodes only site centers and bounds from the map page; imagery URLs, equipment shapes,
and access details are not retained.

```sh
curl -L https://epoch.ai/data/data_centers/data_centers.zip -o epoch-data-centers.zip
curl -L https://epoch.ai/data/ai-data-centers/map -o epoch-map.html
python3 -m datacenter_atlas import-epoch \
  --db atlas.sqlite \
  --input epoch-data-centers.zip \
  --map-html epoch-map.html \
  --retrieved-at 2026-07-18T00:59:24Z \
  --as-of 2026-07-17
```

The current promoted public-stack [2026-07-19 open seed v32](releases/2026-07-19-open-seed-v32/)
contains 74 Epoch-derived AI campuses plus 142 strict official-source campus records and 154 project
rows. Its 370 source-scoped entities comprise 216 campuses and 154 projects; it retains 195 current
pipeline rows and 161 construction-source signals. The release manifest exports 226 claim-linked
evidence rows, while `summary.json` reports 252 evidence observations in the release database;
those denominators are not interchangeable. The release also retains 401 current typed metric
observations across distinct capacity, annual-energy, and PUE metric types, four advisory resolution
candidates, and 139 coordinate-bearing entities. These are entity rows and source-evidence
groupings, not deduplicated physical sites, and the release is not a global census.

Relative to promoted v30, v32 is strictly additive: 11 campuses, 11 projects, 11 exported evidence
rows, 13 database evidence observations, 11 pipeline rows, eight construction-source signals, and
11 current `under_construction` lifecycle observations. Capacity remains 401, resolution candidates
remain four, and coordinate-bearing entities remain 139. The delta adds no geometry, normalized
metric, workload, operating model, or role.

The historical v30 checkpoint was strictly additive relative to v20: 33 campuses, 33 project rows, 33 exported evidence rows,
nine typed metric observations, 33 pipeline rows, 29 construction-source signals, 33 current
lifecycle observations, and 22 source families are added, while all four advisory resolution
candidates remain unchanged.
The lifecycle delta is 29 `under_construction` rows and one each `permitted`, `proposed`, `shell`,
and `site_preparation`. The nine typed additions remain separated as six `critical_it_mw`, one
`generation_nameplate_mw`, and two `grid_connection_mw` observations; generation and grid
connection are not data-centre load, and none is measured operating consumption.

Relative to historical v25, v30 added 12 campuses, 12 projects, 15 exported evidence records, six typed metric
observations, 12 pipeline rows, 12 construction-source signals, and 11 source families. The status
delta is eight `under_construction` and one each `permitted`, `proposed`, `shell`, and
`site_preparation`. The metric delta keeps three planned critical-IT observations totaling 143 MW,
one planned 101 MW generation-nameplate observation, and two contracted grid-connection
observations totaling 380 MW separate. Maincubes BER02 is the only added campus/project pair with
source coordinates; the other 22 entities remain coordinate-null. Four new broad AI workload
observations and one crypto-mining observation are source-scoped labels, not inferred site types.

The historical v20 checkpoint was itself strictly additive relative to v13: 42 campuses, 46 project
rows, 42 evidence rows, 30 typed metric observations, 46 pipeline rows, and 29 construction-source
signals were added, while all four advisory resolution candidates remained unchanged. All 88 added
entities were coordinate-null.
The 46 new lifecycle observations are 27 `under_construction`, 12 `mep_electrical`, three `shell`,
three `site_preparation`, and one `announced`. The capacity delta preserves 27 planned
`critical_it_mw` observations, one planned `generation_nameplate_mw` observation, and two
contracted `grid_connection_mw` observations as three different metric types. Generation and grid
connection are not data-centre load, and none of these rows is measured operating consumption.
Untyped campus, component, portfolio, and greater-than wording remains source metadata rather than
being forced into typed capacity.

At the historical v20 checkpoint, the final Khazna/Yondr tranche was added to accepted v19. Yondr's
third Slough building is `under_construction`, but its 40 MW building statement and the 60 MW-plus
and 100 MW-plus nested
totals remain untyped. Khazna AUH4 and AUH8 are `under_construction`, but their combined 60 MW is not
allocated to either project. QAJ1 is `shell`; its separate design-certification source supports one
planned 100 MW `critical_it_mw` observation and a broad `ai_specialized_unspecified` workload. Tier
III design certification does not advance the lifecycle or establish operation.

The historical v13 checkpoint added 13 coordinate-free campuses and 15 physical-project rows from accepted QTS,
STACK Infrastructure, Digital Realty, CyrusOne, and Colt sources. Eleven lifecycle observations are
`under_construction`, two are `shell`, one is `civil_works`, and one is `site_preparation`. Its only
new typed metrics are four planned, source-scoped `critical_it_mw` rows: Colt London 4 at 31 MW,
CyrusOne MIL1 at 27 MW, Digital Realty's three-facility Dugny campus at 176 MW, and Digital Realty
FRA20 at a nominal approximately 16 MW. Those scopes are not current load, gross facility power,
grid draw, generation, energy consumption, or evidence of operation. QTS Cedar Rapids remains a
likely unresolved overlap with Epoch's coordinate-bearing QTS row; no automatic merge or new
resolution candidate is created.

Historical v12 added ten coordinate-free Microsoft Local campus/project pairs to accepted v11. Four projects
are explicitly `site_preparation`, two `foundations`, three `mep_electrical`, and one `civil_works`.
The pages support only those dated physical stages: later slab, steel, substation, principal-work,
completion, and operating statements remain forecasts. East Point is excluded because its page has
no fresh 2026 dated construction update. The tranche adds no capacity, energy, PUE, workload,
operating model, role, coordinate, completion, operation, or unique-site claim.

Historical v11 added five Vantage/NTT campuses and five project rows. Only NTT Frankfurt's sourced 7.3 MW
expansion has a current construction lifecycle; four stale or forecast-only project narratives do
not. Its ten additional capacity rows brought the v11 total to 358 while preserving source scope:
KIX1 68 MW planned campus critical IT plus a 28 MW first-facility forecast; KUL2's newer 436 MW
planned campus value supersedes rather than adds to the older 256 MW statement; OH1 192 MW planned
campus plus a 64 MW first-building forecast; Frankfurt 70.1 MW operational, 7.3 MW planned
expansion, and source-reported 77.4 MW planned campus maximum; Amsterdam 20.7 MW operational plus
22 MW planned for buildings C/D. Source MVA values remain metadata, and no derived 42.7 MW value is
created.

Historical accepted v10 added three Microsoft Finland campuses and six phase-specific projects. Espoo's second
building, Kirkkonummi's first and second buildings, and Vihti phase 1 are source-reported under
construction; Espoo phase 3 and Vihti phase 2 remain `permitted`, not physical construction. The
greater-than-200 MW Finland PPA is portfolio-procurement metadata, not site capacity. All historical v9
capacity rows remain preserved, including 600 MW contracted and 300 MW planned `critical_it_mw` for
five Applied Digital projects and the separately typed 576 MW planned backup-generation nameplate
calculated from 192 proposed 3 MW generators. Generation is not data-centre load, grid service, or
energy consumption. All-rights-reserved source bodies are not redistributed in the release.

Publication-contract v2 derives GeoJSON and text attribution from every exported claim-evidence
row and describes capacity and energy methods row-by-row. Frozen v6 and v7 retain scientifically
valid source rows but are rejected publication artifacts: their README advertises a nonexistent
`atlas.html`, overgeneralizes one annual-energy model, and omits DTE from bundled attribution. They
remain byte-preserved and are not current output.

Curated locality/county points are approximate. The Finland rows use explicitly guarded rounded
campus-level analyst snapshots with low confidence; OH1's official marker is campus-only; the ten
new Microsoft Local pairs intentionally have no coordinates. None is a source geocode, parcel,
building centroid, or unique-site assertion. Disclosed cooling plans and partner roles remain
source metadata, while co-located generation, statewide energy figures, portfolio PPAs, MVA, and
ambiguous gigawatt-scale compute or campus wording are not promoted to typed IT load, facility
power, or energy. Current, planned, contracted, and forecast metrics remain separate. All four
cross-source resolution candidates are advisory and create no merge. Epoch's lone orphan timeline
name, `EdgeCore Mesa PH03`, has no row in Epoch's 74-center table and is explicitly excluded rather
than synthesized. The frozen Epoch capture manifest is
`8755480ac8797f1067e1a3fc8934661674e0b5129da0833157a51d4e7b82b4db`. The current v32 release
definition is `97662af3ab781b5505de1d436a06cac55002fc332cef641a7f61469486c0f150`; its release manifest is
`85796139cc8245e4318379930a8e83af1c5b32b8d9c109699cb025230daf237c`; its `summary.json` is
`1d9d55c6fcfcdb7d9b44e33387c363c1269c6359b1f9731cca6f0a4203452fd8`; and its focused release test is
`ab709c17c4cf823f839817ef4c769098269b94ef117655c41fedcd5b466de3d2`.
The historical v30 definition and manifest remain
`b89c7414fe9a96ddd2acfff766386dda514d61278dae039d1d70eb490340ef12` and
`35ab5e5939237049296955e129fd969400fb51ce64965216a895f65b10b30619`. The historical v20 release
definition and manifest remain `099f1f519cc7440fa160ed6db7220d91562ae8b1cea6c1ef1305eefbbb5319fd`
and `e45aeeddc2d450a9faebf9f8919e3726dadf2547c95a864c395c75c95302c456`, respectively.
The release is heavily U.S.-weighted and Epoch's selected large AI sites are not a global census.

## Sentinel-2 evidence pilots

The [Colossus 2 pilot](satellite_evidence/colossus-2-2024-2026/) saves exact Earth Search responses,
a two-window catalog manifest, before/after COG windows, an optical-change overlay, review-only
GeoJSON proposals, and a hashed report. It found nine large connected change components in this
known-site AOI with 96.7% of pixels valid in both images. The proposals make no data-centre
identity, lifecycle, power, or operating-status claim.

The [Ada Docklands pilot](satellite_evidence/docklands-2024-2026/) applies the same bounded workflow
to a second known construction project. Its site-cropped pair has complete valid-pixel coverage and
three review-only change components totaling 9,100 m². It also records a rejected cloud-obscured
automatic selection as a pipeline lesson: scene-wide cloud cover is not sufficient without an
AOI-level clear-pixel check.

Build a global, offline review plan from any release GeoJSON without querying a satellite catalog:

```sh
python3 scripts/build_satellite_review_queue.py \
  --input releases/2026-07-17-open-seed/atlas.geojson \
  --output-dir satellite-review-queue \
  --generated-at 2026-07-18T22:00:00Z \
  --baseline-target 2024-06-15 \
  --current-target 2026-06-15
```

The resulting JSONL prioritizes construction, proposed, and unknown-lifecycle entities before
operational sites, then orders missing and older status evidence first within each tier. It supplies
bounded argument arrays for the existing catalog/change scripts. Its immutable three-file bundle
is validated before one directory-atomic publication; reruns accept only a valid byte-identical
bundle. The manifest hash-binds the exact input and queue bytes, binds an adjacent release manifest
when present, and reports country/tier and status-freshness balance. The planner makes no network
request and no imagery-derived identity, lifecycle, operating-status, or power claim. See the
[queue contract](docs/satellite_review_queue.md).

The completed v3 priority run cataloged 65 usable pairs plus nine no-scene outcomes across 74
active-construction entity rows, and 16 usable pairs plus four no-scene outcomes across 20 proposed
rows, with no failed jobs. Two clear-sky change pilots were then reviewed manually: EAT12 was
retained only as a site-aligned change candidate, while the QTS Hillsboro 3 mask was rejected for
site promotion because agricultural and off-site changes dominated it. See the exact hashes and
negative-control rationale in the [batch run record](docs/satellite_batch.md).

The current frozen catalog accounting uses active-001, proposed-001, and cumulative Unknown034 as
three non-overlapping lanes. Unknown034 covers all 6,736 unknown-lifecycle jobs: 4,397 usable pairs,
303 no-scene outcomes, zero failures, and 2,036 pending. Its manifest state is intentionally
`incomplete`: this is a bounded catalog-only checkpoint, not a completed global queue. Across all
6,830 queue jobs, the three lanes contain 4,478 usable pairs, 316 no-scene outcomes, zero failures,
and 2,036 pending. Unknown034 supersedes earlier cumulative unknown checkpoints for current
accounting; their counts must not be added. This pass ran no computer vision or change analysis,
mutated no atlas claim, and inferred no identity, lifecycle, operating status, or power. The
Unknown034 manifest SHA-256 is
`9cc51440c6d0f53a20f45fef61cf33345a47d0dd2f22265b188a692bd3eb6ebd`.
It was continued from a validated copy-on-write clone of the accepted Unknown033 recovery, then
sealed `0555`/`0444` and revalidated offline.

The separate frozen [v2 change checkpoints](docs/satellite_change_batch.md) now process 58 unique
active-lane queue rows across 40 exact AOI geometries. The five-job qualification, later 8-, 9-,
and 21-job checkpoints, and a 15-job edge-reselected checkpoint are machine proposals with no analyst
decisions. Duplicate entity rows can share byte-identical imagery, and AOIs can overlap, so neither
58 nor 40 is a site count. All remain
outside the master, map, ledger, candidate fusion, and calibration; imagery creates no automatic
identity, lifecycle, type, capacity, power, PUE, workload, or energy fact. The qualification
manifest SHA-256 is
`e435666a7148f8dfb24bbd037aeb3555bb59caa5571bdf138b50471e64ff2d78`; the reselected run manifest
SHA-256 is `6932ed40ccdc4650336a3d0716e2ab73aee09f10f1381dc6e8811e4aaf5dbc91`.

Active-001 has 65 completed catalog rows. Their non-overlapping current-output partition is 58
unreviewed algorithm-v2 proposal rows, five historical algorithm-v1-only rows, and two France rows
without any change output after the bounded reselection. Seven active rows have a historical-v1
review, but two of those also have new v2 proposals whose selected scene hashes differ; their old
labels cannot transfer. The historical calibration v4 labels all 43 of its separate input reports as
algorithm v1; its 12 retain and 31 reject decisions do not calibrate v2. A current calibration
requires algorithm-v2 reprocessing and fresh review rather than transferring historical labels.

That exact reprocessing is now complete as numerical evidence. Ten immutable shards cover all 43
historical input specifications once: 36 produced algorithm-v2 comparison bundles and seven stopped
at the declared single-asset boundary with a multi-tile mosaic required. The frozen
[label-blind aggregate](docs/satellite_calibration_aggregate.md) exposes the 36 successful outputs
for fresh review and ledgers the seven blockers separately. It reads no historical retain/reject
label, performs no adjudication, and makes no identity, lifecycle, construction, type, capacity,
power, PUE, workload, energy, accuracy, or calibration claim. Its manifest SHA-256 is
`a1b9b2e76dc4efac8ca77edfec7bb6ca2c2457eaa5395958796acf42729dbca4`.

The subsequent frozen [identity-blind rereview audit](docs/satellite_calibration_v2_blind_rereview.md)
closes reviews for those 36 ready comparisons: 16 retain, 19 reject, and one uncertain, resolved by
28 A/B agreements, seven two-of-three majorities, and one three-way uncertain. Historical labels
were joined only after the blind decisions were fixed. Thirty of 35 binary-comparable rows have the
same raw label as the prior analyst review (85.71428571428571%); this is descriptive agreement, not
accuracy, precision, recall, truth, production calibration, threshold validation, construction
truth, or SemiAnalysis parity. The seven multi-tile rows remain blocked with no v2 decision. V4,
manifest SHA-256
`be0e7042eac7a54697ff526400537fe66211dbbdf7d5a505c541a3a6fc4b590d`, is byte-preserved as rejected
historical evidence: an independent audit proved its successful parent-fsync path could return a
release ID after a public-target substitution. The independently accepted v5 successor has
manifest SHA-256
`dff606bfbd4015c51d24387d4b9a73a48b236895d745b7343aacfe46a5ef57e7`. Fresh QA reproduced its
frozen bytes through both API and CLI publication, verified source and scientific arithmetic,
exercised explicit I/O failures, found no descriptor leaks, and preserved v1 through v4. V5 revalidates the descriptor-bound parent, target, exact frozen file identities,
modes, and bytes after the publication fsync. Its failure recovery recursively deletes nothing;
writer-owned state is safely retained or quarantined, unrelated substitutions are preserved, every
directory-entry mutation is fsynced, and primary plus recovery failures are reported together. The
data arithmetic and review semantics are unchanged, and v1 through v4 remain byte-identical.

The separate accepted frozen [multi-tile mosaic preparation](docs/satellite_mosaic_preparation.md) v6
successor binds six metadata-ready specifications and one still-blocked MRS5 row to 40
exact input-file pins; it downloads or opens no imagery and executes no mosaic. V1 through v5 are
byte-preserved as rejected publication-mechanics evidence. V5 fixed v4's ambiguous mkdir and
sequential final-close defects, but its writer and validator acquisition helpers could open a
descriptor before the outer cleanup ledger owned it. V6 registers every descriptor immediately
after open, attempts all acquired closes, aggregates acquisition and cleanup errors, and reports the
exact requested target plus every allocated staging path. Its manifest SHA-256 is
`f0cb59766c68e7cc54da8f103f7a92a7eb4943e2fe4533702df9d19c0cd366e6`. A fresh independent audit
reproduced every frozen byte through socket-denied API and CLI publication, reconciled all pins,
found no false success or descriptor growth across seven fault scenarios, and passed the 67-test
v1-v6 lineage. The preparation makes no construction, identity, lifecycle, type, operator,
capacity, power, energy, PUE, workload, calibration, or SemiAnalysis-parity claim.

The checked [candidate-fusion v13](candidate_fusion/2026-07-18-osm-planet-priority-v13/) orders
14,324 of the 102,451 Planet structural candidates that have at least one configured review
opportunity. It pins 43 historical algorithm-v1 analyst report/review pairs: 12 retained manual
follow-ups and 31 rejected masks. Its priority tiers contain 28 candidate rows overlapping retained-review AOIs, 1,037
distinct-source-root opportunities, and 13,259 shared-root or queue opportunities. One review AOI
can overlap several candidates. Fusion creates no identity, lifecycle, status, type, workload,
capacity, power, energy, duplicate, or unique-site claim.

## Operating specification

- [Methodology and completeness contract](docs/methodology.md)
- [Source rights registry](docs/source_registry.md)
- [GDELT bulk-news review lane](docs/gdelt_news.md)
- [Bounded Overture building discovery](docs/overture_building_discovery.md)
- [Google Open Buildings Temporal review lane](docs/open_buildings_temporal.md)
- [Microsoft global building-footprint review lane](docs/microsoft_global_ml_building_footprints.md)
- [Label-blind algorithm-v2 numerical aggregate](docs/satellite_calibration_aggregate.md)
- [Algorithm-v2 identity-blind rereview audit](docs/satellite_calibration_v2_blind_rereview.md)
- [Scrutica isolated discovery and release](docs/scrutica.md)
- [PeeringDB rights and source assessment](docs/peeringdb.md)
- [EdgeMode and SEC EDGAR assessment](docs/edgemode.md)
- [EPA ECHO and FRS assessment](docs/epa_echo_frs.md)
- [Ireland planning-application release](docs/ireland_planning_applications.md)
- Official process lanes: [NSW](docs/nsw_major_projects.md),
  [Netherlands](docs/netherlands_koop_official_publications.md),
  [New Zealand](docs/new_zealand_fast_track.md), [Canada IAAC](docs/iaac_registry.md),
  [Chile SEA](docs/chile_sea_pertinence.md), [Germany UVP](docs/germany_uvp_verbund.md),
	  [Finland LVV](docs/finland_lvv_environmental_permits.md),
	  [Denmark Plandata.dk local plans](docs/denmark_plandata_local_plans.md),
	  [Poland GDOŚ/SIOS/Ekoportal](docs/poland_gdos_sios_ekoportal.md),
	  [South Korea EIASS/NIER](docs/south_korea_eiass_nier.md),
	  [Japan MOE data-centre casebook](docs/japan_moe_casebook.md),
	  [Malaysia KPKT OSC 3 Plus](docs/malaysia_kpkt_osc3plus.md),
  [Singapore BCA Green Mark](source_assessments/singapore-bca-green-mark-data-centre-certifications-2005-2026-2026-07-18-v1/README.md),
  [Singapore URA Planning Decisions](docs/singapore_ura_planning_decisions.md),
  [India PARIVESH](docs/india_parivesh_environmental_clearances.md),
  [Thailand ONEP Smart EIA](docs/thailand_onep_smart_eia.md),
  [Spain BOE](docs/spain_boe.md), [Italy MASE](docs/italy_mase_via_vas.md),
  [France IGEDD/Ae](source_assessments/france-igedd-ae-data-centres-2009-2026-2026-07-18-v1/README.md),
  [Brazil PNCP](source_assessments/brazil-pncp-data-centre-publications-2016-2026-2026-07-18-v1/README.md),
  and [Australia EPBC](source_assessments/epbc-public-portal-data-centre-search-2026-07-18-v1/README.md)
- Other source assessments: [Loudoun](docs/loudoun_data_center.md),
  [Virginia DEQ](docs/virginia_deq_air_permits.md), [Prince William](docs/pwc_build_out.md),
  [Cleanview](docs/cleanview.md), and [PJM](docs/pjm_large_load.md)
- [Satellite and computer-vision pipeline](docs/satellite_pipeline.md)
- [Full-Planet OSM blind-tile auxiliary](docs/osm_blind_tile_auxiliary.md)
- [Candidate-independent blind-tile auxiliary integration](docs/blind_tile_auxiliary_integration.md)
- [Deterministic satellite-review queue](docs/satellite_review_queue.md)
- [Resumable satellite catalog batch](docs/satellite_batch.md)
- [Resumable satellite change-analysis batch](docs/satellite_change_batch.md)
- [Federated release index](docs/federated_release_index.md)
- [Candidate-fusion review lane](docs/candidate_fusion.md)
- [Public/open construction master](docs/construction_master.md)
- [Construction map](docs/construction_map.md)
- [Global coverage and field-completeness audit](docs/coverage_audit.md)
- [Current-coverage ledger](docs/current_coverage_ledger.md)
- [SemiAnalysis parity benchmark](docs/benchmark.md)
