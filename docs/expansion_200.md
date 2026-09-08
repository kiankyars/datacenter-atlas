# Expansion from 100 to 200 physical sites

The active request, accepted on 2026-09-08, is to add another 100 data centers. This work targets
200 distinct physical sites in the Verified Construction Core, not 200 project rows or a list of
unreviewed announcements. The published baseline remains the byte-frozen
[v0.17 preview](../verified_construction_core/2026-08-20-preview-v0.17/README.md) at commit
`0a04273a0c6689618f8e9498ac3c5c54ebeaf211`: 100 sites, 103 projects, 40 countries, and 252 evidence
rows. Research handoffs and candidate queues are not additions to that published count.

## Acceptance contract

- Add 100 distinct physical sites after project-to-campus identity review and comparison with
  all 100 baseline sites. Multiple buildings, phases, or aliases within a represented campus do
  not increase the physical-site count.
- Keep the lifecycle reference date at 2026-08-20. Each selected project's authoritative physical
  construction observation must fall between 2026-05-22 and 2026-08-20 inclusive. A later web
  retrieval, page edit, planning permission, construction budget, or expected opening date does
  not refresh the observation. Check authoritative completion and cancellation successors before
  acceptance.
- Bind the exact named project to a reviewed boundary or source-specific locator. Preserve the
  source's precision and explicitly unknown accuracy. A corporate office, locality center,
  industrial-zone centroid, or unrelated neighboring building is not an acceptable substitute.
- Keep lifecycle, identity, geometry, roles, workloads, capacity, and imagery evidence roles
  separate. Select no unsupported role or metric to make a record appear complete.
- Preserve source attribution, rights links, capture-byte hashes, and derivation. Redistribute
  compact factual projections only where justified; do not include raw third-party media or
  documents by default.
- Preserve all baseline records and evidence. If new evidence reveals a baseline error, document
  a versioned correction explicitly rather than rewriting v0.17 or silently carrying the error
  into the expansion.
- Retain at least 40 countries, at least 100 non-US sites, and no country above 40% of the expanded
  cohort. These are expansion review thresholds, not claims about the current research queue.
- Verify the expanded release against its full inputs, inherited records, evidence closure,
  source-selection accounting, and exact physical-site count. Require a byte-exact clean-clone
  rebuild, regression tests, secret scan, and CI before publishing.

## Research lanes

Start with the 48 unselected v97 project rows that already satisfy the temporal/status screen,
then refresh stale projects and identify post-v97 additions using dated authoritative sources.
The 48 are not 48 guaranteed new sites: some are additional phases on existing campuses, some
have unresolved locations, and later completion evidence can supersede their construction status.

The broader v97 research pool contains 385 unselected project rows: 48 need reviewed geometry,
325 fail the 90-day status window, and 12 fail the physical-status test. These are first-failure
categories, not independent quality scores. The source pipeline also contains 49 non-project rows;
they must not be counted as construction projects or added sites.

Research is split across the Americas, Asia, Europe, and Middle East/Africa. Findings must retain
both successful candidates and concrete rejection reasons so later work does not repeat rejected
office pins, stale announcements, completed projects, or unresolved multi-facility portfolios.

## Completion versus final-release readiness

The expansion is complete only when the coherent, verified release contains 200 distinct physical
sites and has been committed and pushed with passing checks. Partial batches are progress, not
completion of this request.

Reaching 200 does not make the product a final v1 release. The existing imagery and blind-review
gaps remain explicit; their coverage denominators must expand with the selected cohort, and
`publishable_as_final` remains false unless all final-release gates are independently satisfied.
The blind-review protocol remains a fixed 20-row sample requiring 19 agreements, drawn from the
full expanded eligible project population. It is not a 20-percent sampling rule, and a sample
restricted to the old baseline cannot certify the expansion.

## First reviewed partial draft

The [initial-three draft](../verified_construction_core/2026-08-20-v0.18-draft-initial-three/README.md)
adds CapitaLand Navi Mumbai Tower 2, CapitaLand DC ITPH Hyderabad, and Goodman's first LAX01
development in Vernon. It contains 103 physical sites, 106 projects, 40 countries, and 259 evidence
rows. The two Indian locators are explicitly operator-published campus points; the Vernon locator
is the official assessor reference point at the owner-bound first-facility street address.

This is 3 of 100 requested additions, not completion or publication of the expanded core.
Lifecycle observations remain July 29 for the two CapitaLand projects and June 30 for LAX01;
September location retrievals do not refresh those dates. No new imagery reviews, power metrics,
roles, workloads, or operating status have been inferred.

Reproduce or validate this opt-in draft with:

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --validate-only
```

The builder refuses to overwrite an existing directory. The public core builder remains on v0.17.

## Cumulative five-site draft

The [cumulative-five draft](../verified_construction_core/2026-08-20-v0.18-draft-initial-five/README.md)
adds Microsoft's Kirkkonummi first building and Espoo second building to the initial three. It
contains 105 physical sites, 108 projects, 40 countries, and 265 evidence rows: 5 of the requested
100 additions. Both the initial-three snapshot and the v0.17 release remain unchanged.

Kirkkonummi's contractor update is dated June 26 and its municipal permit supplies a TM-35
activity-site reference point. Espoo's June 11 minutes explicitly identify the first two buildings
as under construction; the selected second building is bound to permit 2024-1349 and registered
parcel 49-65-3-1. The parcel polygon is a project locator, not a data-center campus boundary.
The adjacent third-building permit does not create another selected construction site.

Imagery coverage remains 10/108 and the blind-review gap remains open. To reproduce or validate:

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch initial-five --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch initial-five --validate-only
```

## Twelve-site reviewed checkpoint

The [second reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-second-reviewed/README.md)
preserves the previous five additions and adds Goodman PAR01, PAR02, AMS01 and FRA02,
Amazon Falls Township, Digital Realty Digital Dulles, and Galaxy Helios Phase II. It contains
112 physical sites, 115 projects, 40 countries, 78 non-US sites, and 295 evidence rows.
This is 12 of the requested 100 additions, with 88 remaining. Both prior draft snapshots
and the public v0.17 release remain unchanged.

The French campuses use exact government house-number points. Amsterdam uses the provincial
notice's first published RD location marker, with the source CRS independently checked.
Frankfurt uses the marker linked in Goodman's own project brochure, not the map viewport center.
These are campus locators; none is promoted to a data-center boundary or construction footprint.

The three US locators have explicitly broader constituent scope: Amazon's building-six parcel,
Digital Dulles' IAD44/B7 operator point, and Helios I's government address-range geocode.
They locate one identified campus apiece, not the particular new hall or phase. The Helios
construction selection is Phase II; completed Phase I is not selected as a construction project.
Freestone remains excluded because its operator/legal-entity identity bridge is unresolved.
The [US research handoff](../research/expansion-200/us-locator-handoff-2026-09-08.json) records the
pre-acceptance evidence and unresolved candidates; the separately pinned batch contract is
the authority for these three admissions. The [Americas review](../research/expansion-200/americas-review-2026-09-08.json)
also preserves the Fox Creek power-plant/data-center scope distinction and unresolved Latin
American locator checks without altering the frozen inventory.

Selected physical observations remain June 30 for the four Goodman projects, July 19 for Amazon,
June 29 for Digital Dulles, and July 6 for Helios Phase II. September identity retrievals do not
advance those dates. No new roles, workloads, power metrics or imagery outcomes are inferred.
Imagery coverage is still 10/115; blind review remains incomplete. Reproduce or validate with:

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch second-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch second-reviewed --validate-only
```
