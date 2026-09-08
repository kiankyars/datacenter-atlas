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

## Twenty-site reviewed checkpoint

The [third reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-third-reviewed/README.md)
adds Goodman MAD01, Iron Mountain LON3, Amsterdam, Madrid MAD-2/3, VA-9, MIA-1 and NJE-1,
and LG Uplus Paju. It contains 120 physical sites, 123 projects, 40 countries, 83 non-US sites,
and 329 evidence rows. This is 20 of the requested 100 additions, with 80 remaining. All earlier
snapshots and the public v0.17 release remain unchanged.

Goodman MAD01 uses the exact coordinate query linked by its own brochure. LON3 uses the
government-hosted site-condition report's National Grid Reference. Iron Mountain Amsterdam
uses the provincial notice's RD location marker. The AMS-2 10 MW / AMS-1 Phase 4 association
is explicitly an analyst identity inference from matching campus, scope and schedule, not an
issuer renaming statement. Historical owner records supply identity only; their older March 31
status context is not selected. The separate 20 MW held-development row stays excluded.
Iron Mountain Madrid uses the exact official street-number point at Calle Mar Egeo 4. Its shared
MAD-2/MAD-3 building and subsequent campus phases count once, separate from Goodman MAD01.

The three US locators use exact Census street-address matches with an explicit NAD83-to-WGS84
transformation. VA-9 is located through its known VA-1 constituent on the same 142-acre Manassas
campus, not through an invented point for the unmatched VA-9 address. MIA-1's later partial
generator-test approval is not a completion or occupancy claim. NJE-1's June 30 row supersedes
the earlier planned-but-not-commenced row without inventing a finer construction stage.

Paju's operator-to-parcel link comes from the municipal notice landing page, while its PDF
supplies parcel 1239-1 and site area. The city factory register's exact historical row matches
that parcel, area and the former Heesung Electronics factory. The attributed OSM representative
point is used only as a former-factory campus locator, not a current data-center footprint or
surveyed boundary. The city text's noncommercial/no-derivatives notice is retained; only minimal
restated factual identity metadata is distributed, not the workbook, source prose or images.

The selected physical dates remain June 30 for the seven European/US projects and June 5 for
Paju. No September retrieval advances the lifecycle cutoff. Imagery remains 10/123, the blind
review remains incomplete, and both completion and final-publication flags remain false.

### Explicit Helios datum correction

The [versioned correction](../sources/verified-construction-core-v0.18-helios-census-datum-correction-v2.json)
records that Census geocoder source coordinates use NAD83 (EPSG:4269), as stated in the official
FAQ. The previous checkpoint had copied those numbers into WGS84 GeoJSON without documenting
the datum transformation. The independently executed PROJ operation leaves this point numerically
unchanged. Its reported operation accuracy is not a site-locator accuracy estimate.

Only the new checkpoint replaces the Helios locator evidence key and updates the method/evidence
references. The physical site, project, identity, raw capture hash/timestamp, coordinates, scope,
unknown positional accuracy and construction observation remain unchanged. Earlier source and
draft bytes are frozen and hash-bound in the correction. The shared Dutch CRS evidence also gains
the newly selected Iron Mountain Amsterdam project association; its factual content is unchanged.
Regression tests constrain these exact differences rather than allowing broad inherited rewrites.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch third-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch third-reviewed --validate-only
```

## Twenty-eight-site reviewed checkpoint

The [fourth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-fourth-reviewed/README.md)
adds NEXTDC M2, M3, S3 and S4, MERLIN Bilbao-Arasur and Lisbon, Microsoft La Porte and Meta Lebanon.
It contains 128 physical sites, 131 projects, 40 countries, 89 non-US sites and 362 evidence rows.
This is 28 of the requested 100 additions, with 72 remaining. Every preceding project, site and
evidence row is unchanged. The public v0.17 release and all earlier checkpoints remain frozen.

NEXTDC's August 27 results explicitly report the named remaining construction inventory at
June 30. That retrospective observation date is selected; publication after the cutoff does not
become a later construction date. M2/M3/S3 retain the reported M&E fit-out scope and S4 retains
generic construction. Delivered halls and approval-dependent pipeline are excluded. M2 uses the
operator's directions-link destination. M3 and S3 use attributed community campus points, with
their exact code/address identity constraints retained. M3's conflicting operator overview marker
is recorded and unselected, supported by independent street-address and council identity checks.
S4 uses the named NSW project marker, not the wrong Artarmon search result or default map center.

Bilbao-Arasur selects Building 2 once at the existing multi-building campus, with June 30
half-year work-update evidence. Its owner-published location link resolves to a literal coordinate
query, whose response headers are hash-bound separately from the empty body. Lisbon's two
Phase II buildings count as one campus, with July 27 datelined continuing work and Edged's literal
site coordinates. Existing Phase I operations and later same-campus phases do not add sites.
Publisher work-update photographs are not independent Atlas imagery reviews, and their separate
camera dates remain unknown.

La Porte selects the June 18 first-phase construction start. The July-only grading update is
corroboration, not a fabricated day inferred from a page edit; vertical construction is still future
in that update. The exact government parcel is a 215.361-acre constituent of the approximately
500-acre first-phase campus, not its complete boundary or the proposed eastern expansion.
Lebanon's July 6 municipal minutes explicitly link Orla, Domino and Meta to a campus under
construction. Its exact DNR detention-outfall permit reference locates the campus at Deer Creek,
not a data-center building. The service's Web Mercator-to-WGS84 conversion is independently
checked without claiming to verify the older UTM derivation or improve positional accuracy.

All eight locators retain explicit campus-locator scope and unknown positional accuracy.
No new roles, power metrics, workloads or operating status are inferred. Imagery remains 10/131;
blind review remains incomplete, with the fixed 20-row/19-agreement protocol covering the full
eligible population. Both objective-completion and final-publication flags remain false.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch fourth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch fourth-reviewed --validate-only
```

## Thirty-two-site reviewed checkpoint

The [fifth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-fifth-reviewed/README.md)
adds NEXTDC M4, GE1 and KL1, and MERLIN Edged Madrid-Getafe II. It contains 132 physical sites,
135 projects, 40 countries, 93 non-US sites and 386 evidence rows. This is 32 of the requested
100 additions, with 68 remaining. All preceding project, site and evidence rows remain unchanged;
the public v0.17 release and earlier checkpoints are frozen.

The NEXTDC observations are expressly dated June 30, despite August 27 publication. M4 selects
early works as site preparation; its historical demolition and planning approval are not the
selected construction evidence. GE1 retains generic construction status. Its exact Next DC Corio
application is associated with the operator and builder's GE1 Corio identity by explicit analyst
inference, not a literal government code-to-parcel statement. Both Australian points come from
Vicmap's exact primary virtual address records, not surveyed entrances or construction footprints.
Vicmap's CC BY 4.0 terms and exclusions are retained with source attribution.

KL1's May 14 opening is a predecessor scope check: the June 30 inventory separately distinguishes
delivered halls, remaining fit-out and future plans. Only remaining fit-out is selected. Its named
OSM building point is bound by operator, code, address and facility URL. The road-only operator
directions point and duplicate same-campus industrial-landuse feature are not selected. Community
geometry remains attributed and ODbL licensed; no capacity or operating status is inferred.

Getafe II selects June 30 project-specific demolition as physical site preparation. July 27
continuing-work evidence corroborates the scope. The MAD02 specification sheet literally prints
its campus coordinates and Calle Fundidores 2 address; separate Getafe I is at Fundidores 40.
Matching the report's MAD-GET II code to MAD02 is explicit analyst identity inference. The Getafe II
page's inconsistent, undated 20 MW "Now Open" block is recorded, not erased or treated as dated
completion of MAD02. The sheet's older design-stage forecast and generic footer route do not
override the named identity and dated physical-work disclosure.

All four source-specific points are campus locators with unknown positional accuracy. No new
roles, power metrics, workloads or independent imagery reviews are selected. Imagery remains
10/135; the fixed 20-row/19-agreement blind-review protocol covers the full eligible population
and remains incomplete. Objective-completion and final-publication flags remain false.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch fifth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch fifth-reviewed --validate-only
```

## Thirty-eight-site reviewed checkpoint

The [sixth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-sixth-reviewed/README.md)
adds AI Tech Tomakomai, noris FRA1 Schwalbach, Nebius Pajarila Lappeenranta, FlexBase Laufenburg,
Applied Digital Polaris Forge 1 Ellendale and Polaris Forge 2 Harwood. It contains 138 physical
sites, 141 projects, 40 countries, 97 non-US sites and 419 evidence rows. This is 38 of the
requested 100 additions, with 62 remaining. All prior project, site and evidence rows are
unchanged; the public v0.17 release and preceding draft snapshots remain frozen.

Tomakomai selects June 19 active grading, piling and concrete foundations. The exact corporate
project parcel, Kashiwabara 32-17, is bound by the issuer's acquisition disclosure. AIGID's
MOJ-derived polygon is retained as a community-converted cadastral reference, not an official
data-center boundary. Declared CRS84 output, graphically measured source accuracy limitations,
custom underlying MOJ reuse restrictions and attribution/modification notices remain explicit.
Phase II and its substation do not add another site. The September lease-MOU expiry is a
post-cutoff commercial event, not an inferred construction cancellation.

Schwalbach's June 10 contractor statement confirms actual work beyond the June 9 ceremony.
The later syndicated release is not a new start. Its named OSM FRA1 enclosure point retains the
street-spelling discrepancy and community authority. Pajarila selects Fira's August 11 physical
update without inventing a day for July commencement. The municipal piling notice binds the
exact address and parcel; the city's address search and explicit EPSG:4326 transform supply a
campus point. An unverified native EPSG code is not guessed, and two plots count once.

Laufenburg selects ERNE's June 18 excavated-pit update for the new mixed-use building containing
a data center and battery installation. The OSM technology-centre point is distinct from the
existing office. Neither battery capacity nor the whole mixed-use area becomes data-center
capacity. The September 1 excavation-completion update describes continuing building work;
it does not refresh the selected pre-cutoff observation or establish completed operation.

The July 27 issuer update explicitly names remaining PF1 buildings and PF2 in construction.
Delivered PF1 halls, operating crypto hosting and future financing are excluded. PF1's government
NAD83 generator reference point is bound through exact filed campus lease addresses and transformed
to WGS84; it locates a constituent of the campus, not the selected remaining hall. PF2 uses the
exact APLD FAR-01 county parcel at the government data-center-associated generator address.
The native Web Mercator transformation was independently checked. Its public-domain, reference-only
rights statement is retained; neither locator is promoted to a complete construction boundary.

Microsoft Vaughan remains excluded. Its later-published certificate reports July 15 substantial
completion of the main shell and administrative fit-out, while current remaining construction
scope is insufficiently separated. A held research package is not an additional site.

All six additions retain unknown positional accuracy and campus-locator scope. No roles,
workloads, capacities, operations or independent imagery results are inferred. Imagery remains
10/141; the fixed 20-row/19-agreement blind review remains incomplete. Both completion and
final-publication flags are false, and the 100 non-US expansion threshold is not yet reached.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch sixth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch sixth-reviewed --validate-only
```
