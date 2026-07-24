# Global coverage and field-completeness audit

The coverage audit is an immutable accounting layer over a federated release index. It measures
what the pinned child releases actually contain by child release, source family, and country. It
does not rewrite a release, combine licenses, merge entities, adjudicate advisory relationships,
promote review leads, or estimate unique physical sites.

The checked `public-open-coverage-v10` audit covers the current publication-safe federation and
binds these exact inputs:

- `releases/2026-07-18-global-open-v3/manifest.json` at
  `fe14c1b264ce7d5f589c717147e584f7ace97b832b0987389f2ee03ded6bb562`;
- `releases/2026-07-19-open-seed-v20/manifest.json` at
  `e45aeeddc2d450a9faebf9f8919e3726dadf2547c95a864c395c75c95302c456`;
- `releases/2026-07-18-osm-fuzzy-review-v2/manifest.json` at
  `60ecf42e7b260c2f1822c65b9efb184e9fdbca3a36bd4b467960d26e8c9bb07c`;
- `federated_indexes/2026-07-19-public-open-v9/manifest.json` at
  `9dee9fc48ce8dd4d729bbd45fec7d976f79af041894ecb1ef5a9401f7f4f04c5`.

The open-seed v20 definition SHA-256 is
`099f1f519cc7440fa160ed6db7220d91562ae8b1cea6c1ef1305eefbbb5319fd`. The federation v9
definition SHA-256 is `3c7a9b13cda5ffd5cc4791b47f7f93266d441c37a10cd44883a7caff15b1d9f1`, and its exact
`federated-index.json` SHA-256 is
`600b34d8807fa06b2ea2e098c39f72d2299a8a485ae08a41b66c9b334bdc4cb1`.

The earlier public-open v1-v9, provisional-open v1, and Scrutica-inclusive four-layer v1 audits
remain immutable and revalidate byte-for-byte. None is the current public coverage view. Public-open
v7 is explicitly rejected as current because its legacy benchmark comparison hardcoded permits as
absent despite permit-process evidence in open-seed v9; v8 fixes that semantic output without
rewriting v7. The prior public-open v9 audit remains pinned to federation v8 and open-seed v13; its
320 groups, 1,819 gaps, definition SHA-256
`459f49d97e8cb884dc5c33c6dc15852c9fbcdf0769c71739b155367923c03997`, and manifest SHA-256
`657216c910e300314f691e1e726a188c24095bd7b4ec000a97d2a4db7e4ff247` remain historical facts.
The four-layer artifact is local-research-only because its Scrutica child is quarantined pending
upstream-rights evidence.

The federation and all child file inventories are revalidated before the audit reads
`atlas.geojson` and `evidence.csv`. An input hash change fails closed rather than silently changing
the result.

## Metrics and denominators

`coverage.csv` has three explicit aggregation levels: `release`, `release_source`, and
`release_source_country`. `__ALL__` denotes a roll-up. `__UNRESOLVED__` denotes an entity row for
which no country label is available. Country resolution uses, in order, the exported country,
administrative country, and legacy `tags.country`; ISO coverage is reported separately so an older
source label is not misrepresented as a boundary-derived assignment.

Every completeness rate uses source-scoped rows in that exact group as its denominator. The audit
measures:

- valid longitude/latitude and country/ISO coverage;
- source-declared campus, facility, building, and project labels;
- lifecycle status, date, evidence, method, and age buckets relative to the audit date;
- exact `under_construction` and forward-pipeline source rows plus status evidence identifiers;
- capacity-bearing entities and observation distributions by metric, stage, method, and confidence;
- annual-energy method and `method|evidence source family|license` provenance;
- operating-model and workload values and whether their evidence identifiers resolve;
- review-only and non-review rows separately.

Status freshness buckets are `0_90_days`, `91_365_days`, `366_plus_days`, `future`, `invalid`, and
`missing`. A distinct status evidence identifier is an evidence observation, not a site. Capacity
counts are observations, not values that can be summed across stages or overlapping releases.
Annual-energy observations are never called metered unless their own method establishes that.
`informative_lifecycle_status_rows` excludes both `unknown` and review-only `lead` values; the raw
status-claim coverage remains separate so a well-provenanced unknown is not presented as a known
real-world lifecycle.

The fuzzy child retains `facility` as its source-declared schema kind, but the audit places all
6,130 rows in `review_only_rows` and excludes them from
`non_review_source_declared_entity_kind_counts`. Its 18 exact lifecycle-tag observations are
`review_only_under_construction_lead_rows`, not confirmed construction facilities. Across the three
public/open children there are 186 non-review and 18 review-only under-construction rows, tied to 143
construction evidence observations. The audit always sets
`candidate_rows_counted_as_facilities` to false. The 100,409 resolution candidates remain
advisory records; `confirmed_duplicate_relationships` and `unique_physical_sites` are both null.

Open-seed v20 retains the Epoch QTS Cedar Rapids campus, an official-source QTS Cedar Rapids campus,
and its current-development project as three source-scoped rows. None appears in the advisory
resolution candidates. The audit does not merge them or assert how many physical sites they
represent; that unresolved identity remains covered by the global high-severity
`unique_physical_sites` gap rather than a named QTS-specific overlap decision.

For the SemiAnalysis methodology comparison, v10 accepts only a canonical definition-level mapping
from an exact child release and evidence ID. Five references resolve to an NC DEQ preliminary
determination, Indiana IDEM preliminary findings, the Wisconsin DNR Port Washington environmental
review page, an ND DEQ air-quality effects analysis, and an Environment Agency permit-application
supporting report. The emitted classification calls them permitting-process evidence only; it does
not assert a granted permit, project approval, or physical construction. Power-data status is
derived from actual capacity observations rather than caller classification. Empty property-record,
FOIA, satellite-imagery, and computer-vision mappings remain explicitly absent from the audited
children.

## Outputs and validation

Build the checked audit without network access:

```sh
python3 scripts/build_coverage_audit.py \
  --definition sources/coverage-audit-2026-07-19-public-open-v10.json \
  --output-dir audits/2026-07-19-public-open-coverage-v10
```

The output directory is closed and contains exactly:

- `coverage-audit.json`: complete semantics, input checkpoints, totals, groups, and public
  benchmark comparison;
- `coverage.csv`: the same 372 aggregation groups in a flat form, with deterministic compact JSON
  cells for distributions;
- `gap-registry.json`: deterministic gap IDs, scope, field, severity, affected rows, denominator,
  and coverage;
- `REPORT.md`: human-readable boundary and summary;
- `manifest.json`: exact input and output checkpoints;
- `manifest.sha256`: SHA-256 of the exact manifest bytes.

The current audit covers 15,707 source-scoped rows—9,577 non-review and 6,130 review-only—and
publishes 2,063 deterministic gap entries. It contains 1,178 capacity observations, including 483
annual-energy observations that are all explicitly modeled rather than metered. Its definition
SHA-256 is `17dbc93024e49a9a12af31452c4c97a7c521e612472462031fe3a76deb817eee`, and its manifest
SHA-256 is `ef874db51e442cee124c47316ccb0bc075121ad47e43e248f6e4d294c577f83e`.

The local four-layer audit covers 19,625 rows and 2,010 gaps, but its extra 4,120 Scrutica rows are
not redistribution-cleared. Those source-scoped arithmetic totals are useful for local gap analysis
only and cannot be substituted for the public audit or a unique-site count.

First publication writes and fsyncs a sibling staging directory, validates it, and performs one
rename. A valid byte-identical existing output is accepted idempotently. An invalid or different
existing directory is never overwritten. `validate_coverage_audit(path, definition_path=...)`
rebuilds against all exact external inputs and requires byte equality.

## Public SemiAnalysis comparison boundary

The audit compares only to public SemiAnalysis statements. Its public product page describes more
than 5,000 facilities, hyperscale-through-colocation scope, permits, property records, FOIA, power
data, satellite imagery/computer vision, critical IT, PUE, utility power, annual consumption, and
site/cluster/region capacity. A public March 2026 article additionally describes quarter-by-quarter
2017–2032 tracking and precise PJM construction timelines:

- <https://semianalysis.com/models-research/>
- <https://newsletter.semianalysis.com/p/are-ai-datacenters-increasing-electric>

The Atlas total cannot be compared to the public facility count because Atlas rows span source
versions and entity kinds and have not been cross-source-deduplicated. The licensed SemiAnalysis
row-level export was not available. Both `licensed_row_level_benchmark.status` and
`overall_parity.status` therefore remain `pending`.

## Fusion-gate contract

A later cross-source fusion gate should consume the audit dimensions, not its totals as site
counts. At minimum retain `child_release`, release manifest hash, `release_review_only`,
`source_family`, normalized country/ISO, source entity kind, coordinates, lifecycle/status date and
evidence ID, capacity metric/stage/method/confidence/evidence ID, annual-energy provenance,
operating-model/workload evidence IDs, and upstream source identity. It should also consume these
coverage flags before accepting a match:

- candidate/review-only versus non-review scope;
- missing or stale lifecycle evidence;
- unresolved country or coordinates;
- modeled versus reported or metered capacity/energy;
- evidence-source-family independence;
- source-declared building/campus/facility/project kind;
- advisory relationship status versus evidence-backed adjudication.

Fusion must preserve one-to-many campus/building/project relationships. A similarity link cannot
become a duplicate, a candidate cannot become a facility, and two source rows cannot become one
physical site until an evidence-backed adjudication record says so.
