# Construction master

The construction master is the deterministic public/open row ledger for construction discovery. It is an observation ledger, not a global site census or an entity-resolution output.

## Frozen v13 scope

The current bundle is `construction_master/2026-07-19-public-open-v13`. Its 109,107 rows use three non-overlapping evidence tiers:

- Tier A: 315 source-supported construction or pipeline observations. These are the only rows included in construction arithmetic: 195 from open-seed v32 and 120 from global-open-v3. Relative to v12, v13 adds exactly 11 source-supported project observations, all `under_construction` and coordinate-null. The delta adds no normalized capacity, annual energy, PUE, untyped power statement, workload, operating model, role, geometry, or independent verification. The historical v11-to-v12 delta remains exactly 33 project observations: 29 `under_construction` and one each `permitted`, `proposed`, `shell`, and `site_preparation`. Only maincubes BER02 in that historical delta carries source coordinates; the other 32 remain coordinate-null. Five v12 additions preserve source-reported planned `critical_it_mw`: 48, 18, 20, 25, and 7 MW. They are not current load, grid demand, generation, consumption, or evidence of operation. Four v12 additions preserve broad `ai_specialized_unspecified` workload and one preserves `crypto_mining`; none is copied to other rows. Independent construction verification remains zero.
- Tier B: 6,298 review leads. This comprises 6,130 fuzzy OpenStreetMap rows, nine EdgeMode/SEC project leads, 114 Ireland planning observations, three England planning observations, 22 NSW Major Projects observations, 13 Netherlands KOOP permit observations, three New Zealand Fast-track observations, and four France IGEDD environmental-opinion observations. Portal, permit, and environmental-review stages do not establish physical lifecycle, construction, or operation. The NSW rows retain ten numeric source phrases as untyped text. The New Zealand rows retain source-declared `hyperscale` and `artificial_intelligence` wording within proposal scope with `operationally_verified: false`. The master accepts no relationship or merge from these lanes.
- Tier C: 102,494 discovery observations. This comprises 102,451 OSM Planet structural candidates plus 43 Sentinel-2 analyst decisions. Structural geometry and imagery change do not establish data-centre identity, lifecycle, capacity, power, workload, or operating status.

Tier A contains 226 `under_construction`, 27 `expansion`, 22 `proposed`, 15 `mep_electrical`, nine `site_preparation`, six `shell`, three each of `announced` and `permitted`, and two each of `foundations` and `civil_works`. Its canonical arithmetic projection SHA-256 is `0bdebf32e3df7af34aa1a234c90c1da8c2796ae9efb3b41e50b0bbb01d5b097c`. These are source-supported observation rows, not independently verified construction sites and not a unique physical-site count; independently verified construction remains zero.

Twelve Netherlands rows carry official ETRS89 map anchors. Eight have one distinct source point. Four have multiple source points whose maximum pairwise haversine span is at most 100 metres; those rows use the arithmetic mean as a review-map anchor. Wider point sets fail closed to no coordinate. The source evidence retains every original point.

The France lane contains three direct data-centre project observations and one ancillary grid-connection follow-up from the frozen IGEDD release. All four remain Tier B, review-only, outside construction arithmetic, unresolved to a unique facility, and without coordinates or lifecycle status. The ancillary observation keeps its source-stated relationship to Digital MRS6 as advisory evidence only; it is not merged into the direct row. The 13 source metrics are copied without conversion or relabeling. Only two values explicitly scoped to information-technology uses remain `it_power_capacity`. Backup thermal/electrical capacity, UPS/battery power, battery recharge power, and requested grid-connection power remain distinct metric types and are never treated as IT capacity, facility load, or consumption. The two annual-energy values and one target PUE remain source projections rather than measured operation.

## Row contract

Every JSONL row includes:

- a UUID5 stable row ID, evidence tier, observation kind, and evidence scope;
- pinned source artifact, release, record, entity, evidence, manifest, and content hashes where available;
- source roots, upstream license, URL, retrieval date, and compact evidence metadata;
- entity kind, name, address, coordinates, coordinate method, country, and ISO codes without filling unsupported values;
- reported lifecycle/date alongside a normalized status;
- explicit construction support, verification status, method, and confidence;
- explicit identity status and confidence;
- typed capacity observations with value, unit, metric, stage, scope, and confidence;
- annual-energy and PUE observations kept separate from other capacity metrics;
- unresolved source power statements kept untyped;
- operating-model and workload observations kept separate;
- satellite job/scene/decision links and advisory resolution links;
- first and last evidence dates; and
- an explicit disposition, construction-arithmetic flag, exclusion reason, and `unique_site_counted: false`.

`construction-master.jsonl` is canonical. `construction-master.csv` is a flattened representation; every nested field is encoded as canonical JSON so no observation content is dropped.

## Advisory inputs

Candidate fusion v13 supplies opportunity overlays for 14,324 structural rows; 88,127 structural rows have no fusion opportunity. The overlay does not alter the structural primary row or infer a site. Its 43 historical algorithm-v1 analyst report/review pairs come from the hash-pinned v13 definition and manifest. The construction-master manifest checkpoints and deduplicates each report and review; those labels do not calibrate v2.

The frozen within-release resolver contributes 8,586 advisory links: 5,936 shared-identity candidates, 588 tight same-site candidates, and 2,062 part-of candidates. Only 124 links touch at least one of the 315 Tier A master rows; 8,462 have no master-row endpoint because this ledger intentionally excludes non-pipeline entity rows. The 124 links create 185 endpoint attachments across 119 master rows. Accepted relationships and automatic merges both remain zero.

V13 pins active-001, proposed-001, and cumulative Unknown030 catalog state. The three lanes report 4,431 completed scene pairs, 313 no-scene jobs, zero failures, and 2,086 pending jobs. Unknown030 itself remains incomplete at 4,350 completed, 300 no-scene, 2,086 pending, and zero failed jobs. This does not rewrite candidate-fusion v13: its 43 historical algorithm-v1 reviews retain their exact active-001, proposed-001, Unknown010, Unknown013, and Unknown015 source-batch paths and hashes. Unknown030 is attached only as incomplete cumulative catalog state. The reviews remain separate Tier C observations: 12 retained for manual follow-up and 31 rejected for site promotion. They create no imagery-derived identity, lifecycle, operating-status, type, capacity, power, or energy claims. Algorithm-v2 proposals and calibration remain outside this master. Unknown026 through Unknown029 are preserved historical catalog progress and are not additive current inputs.

## Capacity and gaps

The bundle reports 115,402 source-evidence records plus exact observation counts and row-level null/gap rates in `coverage.json`. It contains 233 typed capacity observations excluding energy and PUE, 73 annual-energy observations, two PUE observations, and 23 untyped capacity or power statements. V13 adds none of these metrics. The five planned critical-IT additions arrived in historical v12; they retain their project scope, stage, method, evidence, and unit. Existing Applied Digital rows separately preserve 600 MW contracted plus 300 MW planned `critical_it_mw`; a separately recorded 576 MW planned backup-generation nameplate remains excluded from construction arithmetic and is not data-centre load. Thirteen untyped statements come from EdgeMode and ten from NSW. The France lane contributes ten exact typed capacity/support/grid metrics, two projected annual-energy metrics, and one target PUE metric. The other official process lanes contribute no typed capacity, annual energy, or PUE observations. Unsupported values remain null.

The two operating-model observations are source-supported `wholesale_colocation` on the shared CoreWeave Ellendale row and `retail_colocation` on Equinix DB7x. The 103 workload observations comprise source-supported Tier A fields, operationally unverified intended EdgeMode fields, one source-declared proposed New Zealand AI characterization, four newly added broad AI classifications, and one newly added crypto-mining classification. No campus-level, generation, or contextual federation claim is silently copied onto a project row.

## Build and offline validation

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/build_construction_master.py \
  --definition sources/construction-master-2026-07-19-public-open-v13.json \
  --output construction_master/2026-07-19-public-open-v13
```

The writer refuses an existing destination and atomically publishes a fully staged bundle. Validate every pinned input and regenerate every output byte without network access with:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/build_construction_master.py \
  --definition sources/construction-master-2026-07-19-public-open-v13.json \
  --output construction_master/2026-07-19-public-open-v13 \
  --validate-only
```

New bundles are frozen `0555` with files `0444` by default. The v13 definition pins open-seed v32, public federation v11, permit-aware coverage audit v12, the unchanged global release, structural shortlist, candidate-fusion v13, within-release advisory output, active-001, proposed-001, and cumulative Unknown030. Federation and audit arithmetic is contextual only and is not imported as rows or sites. The definition also pins the NSW, Netherlands, New Zealand, and France assessment/observation/manifest bytes plus the France source definition and schema. The manifest records all 43 deduplicated analyst report/review checkpoints. V1 through v12 definitions and bundles remain byte-for-byte reproducible historical artifacts; relative to v12, v13 adds exactly the 11 source-supported coordinate-null project observations described above.

## Rights and units

The public/open release retains per-row provenance and rights. Structural and fuzzy discovery use OpenStreetMap under ODbL 1.0. The open seed includes Epoch AI under CC BY 4.0 and Wikidata under CC0. Strict company-source rows contain only compact factual observations linked to official disclosures under their source-specific terms; page prose and images are not redistributed or relicensed. Ireland uses `IrishPlanningApplications` under CC BY 4.0. England uses Planning Data under the Open Government Licence v3.0 with `© Crown copyright and database right 2026` preserved. NSW contains department metadata under CC BY 4.0 and excludes mixed-rights HTML and attachments. Netherlands contains official-publication metadata and selected official text in the assessed CC0 1.0 scope, subject to express notices. New Zealand contains bounded official page text under CC BY-SA 4.0 or CC BY 4.0 and excludes images, plans, comments, attachments, and third-party material. France IGEDD derived factual rows use the Licence Ouverte / Open Licence Etalab 2.0; raw HTML and PDFs are not redistributed. Sentinel-2 records retain modified Copernicus attribution and Earth Search catalog links. EdgeMode rows contain compact facts from public SEC filings rather than filing text.

Construction arithmetic is measured in source-supported observation rows, not unique sites. Capacity fields retain their source metric and unit. France annual energy remains `GWh/year` because the source uses that unit, and target PUE remains a `ratio`; no conversion is applied. Unresolved power statements remain untyped rather than being forced into MW. No metric is imputed from planning descriptions, footprints, imagery, or other discovery signals.

## Limitations

The master does not claim global completeness, benchmark parity, independently verified construction for all Tier A rows, accepted cross-source identity resolution, or a unique physical-site count. Spain BOE, Italy MASE VIA/VAS, Brazil, Germany UVP, IAAC, Chile SEA, and Australia EPBC lanes are excluded from v13. Scrutica, PeeringDB payloads, and other restricted or non-redistributable row data are also absent.
