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

## Forty-site reviewed checkpoint

The [seventh reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-seventh-reviewed/README.md)
adds DVZ Schwerin and Applied Digital Delta Forge 1 near Boyce, Louisiana. It contains 140
physical sites, 143 projects, 40 countries, 98 non-US sites and 437 evidence rows. This is
40 of the requested 100 additions, with 60 remaining. Every prior project, site and evidence
row is unchanged. The public v0.17 release and all earlier checkpoints remain frozen.

Schwerin's July 31 magazine reports the unfinished shell and ongoing utility connections.
Its exact dated operator news card, issue announcement and PDF download link are separately
bound. The inconsistent 2025/2026 foundation year remains unresolved and is not the selected
observation. The operator's site-planning deck and TED address clause bind the new building
to the existing campus. The named OSM campus center is not either nearby office feature,
the new building footprint, a surveyed boundary or the active-work extent.

Delta Forge 1 retains the July 27 issuer statement explicitly naming current construction.
Its selected point is independently reproduced from the named OSM construction-fence polygon.
Government, owner and contractor records corroborate the exact campus identity through
15 James Road, AI 250709 and construction well 40-0252. The public rehosted documents have
not been byte-matched to agency originals; this limitation stays explicit. The well's datum
is unstated, so its coordinate is corroboration only, not transformed or selected geometry.
Completed wells and a cleared dust deficiency do not establish a completed data center.
AEX01, AEX02 and their construction wells count as one physical campus.

Both new locators retain community authority and unknown positional accuracy. No new roles,
capacities, workloads, operations or independent imagery outcomes are inferred. Imagery
remains 10/143; the fixed 20-row/19-agreement blind review remains incomplete. Completion
and final-publication flags remain false, and the 100 non-US threshold is not yet reached.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch seventh-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch seventh-reviewed --validate-only
```

## Forty-three-site reviewed checkpoint

The [eighth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-eighth-reviewed/README.md)
adds Nxtra Lagos Eko Atlantic LOS1, Ascenty Sumaré and Schwarz Digits Lübbenau. It contains
143 physical sites, 146 projects, 41 countries, 101 non-US sites and 459 evidence rows.
This is 43 of the requested 100 additions, with 57 remaining. The non-US threshold is now met,
but the total-site objective is not. Every earlier project, site, evidence row and GeoJSON
feature remains unchanged; the public v0.17 release remains frozen at 100 sites.

Lagos preserves an explicit identity inference: the July 23 CEO transcript names a large
Nigerian data center, not LOS1. The sole named Nigeria hyperscale project, first-Nigeria
disclosure and LOS1 page establish the association. Its operator-authored point and Google
Maps coordinate contract are bound separately. A secondary completed claim linked to an old
forecast does not override the later primary construction statement. Nigeria is not Niger.

Sumaré uses the May 28 CEO construction post, with executive authority independently bound
to the operator's Code of Conduct. Full readable legacy brochure pages establish the shared
SUM01/SUM03 campus. SUM01's literal operator point is a broad constituent-campus locator,
not the new SUM03 footprint. The static frontend marker trace and WGS84 provider contract
are bound without distributing source code or making map-service requests. Old brochure
status, operating SUM01, other campus phases and aggregate power are not new admissions.

Lübbenau's August 24 project-manager article explicitly reports August 18 building progress.
The observation is within the cutoff even though publication is later. An operator job names
the exact Kraftwerkstraße 24 address, matching one government house-number object. LGB's
address-building-or-parcel scope, EPSG:4326 and attribution license remain explicit; no campus
boundary, entrance, new-hall footprint or numeric accuracy is claimed.

The research packets retain Heusenstamm's mixed-use-roadwork scope gap, FRA5's unresolved
locator, the failed TYO05 exact-parcel lookup, completed MEL01 ambiguity, and Equinix's
financial-expansion/physical-status distinction. Fairview Level 2 commissioning has a real
Q2 filing lead, but its raw capture and exact locator remain unclosed. None is admitted here.
Imagery coverage remains 10/146 and the fixed 20-row/19-agreement blind review is incomplete.
Both objective completion and final-publication flags remain false.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch eighth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch eighth-reviewed --validate-only
```

## Forty-six-site reviewed checkpoint

The [ninth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-ninth-reviewed/README.md)
adds Vantage Winterthur, Hut 8 River Bend and Hut 8 Beacon Point. It contains 146 physical
sites, 149 projects, 41 countries, 102 non-US sites and 479 evidence rows. This is 46 of the
requested 100 additions, with 54 remaining. All 143 previous sites, 146 previous projects,
459 previous evidence rows and their GeoJSON features remain unchanged. The public v0.17
release is still frozen at 100 sites.

Winterthur retains an explicit phase-identity inference. ERNE's July 30 current-finishing
article names Vantage, Winterthur and DPR, not the ZRH12 code. DPR's named ZRH12 Building 2
project and separate ERNE trade-partner disclosure bind that phase. Completed ZRH11 and
future ZRH13 do not become separate sites. The exact operator address, Fabrikstrasse 12,
8404 Winterthur, matches one record in the complete official address download: EGAID
102586517. The selected point is transformed from that record's LV95 coordinates using
the official REFRAME service. The download checksum, full CSV member checksum, unique-row
match, coordinate specification and attribution terms are independently checked. Full PDF
pages establish REFRAME's coordinate contract and Report A public-domain classification.
The operator's conflicting embedded pin is excluded; the selected building-address point
locates the shared campus, not the ZRH12 footprint or a surveyed boundary.

River Bend and Beacon Point use the issuer's August 4 current-construction statement and
project-specific physical-work descriptions. Quarter milestones are not assigned an exact
August 4 occurrence date. Phase 2 leasing, financial construction categories and forecast
2027 delivery are not additional physical projects, capacity observations or completed halls.
Beacon Point's later generic CMS Commercialization label remains an explicit conflict,
not lifecycle corroboration or proof that work stopped. The August 10 primary successor
still describes the campus under development.

Both Hut 8 locations are exact named operator markers, traced from the platform's campus
records through its Mapbox implementation with provider CRS documentation bound. River
Bend's displayed marker uses the operator's six-decimal rounding; raw input precision is
preserved in provenance. Neither marker is a boundary, phase footprint or accuracy estimate.
Hut 8 rights remain reserved: the draft retains isolated coordinates and independently
restated facts, not publisher prose, code, maps or imagery. No open license is invented.

Fresh hold packets preserve FRA5's forum-marker/plan-location conflict, HIVE Yguazú's
unclosed locator, Sabey Umatilla and Bell Sherwood's location/rights gaps, and the APAC
date/identity conflicts. Fairview's Q2 filing is now captured and supports Level 2
commissioning, but its exact locator remains unclosed. These candidates are not admitted.

The checkpoint adds no normalized roles, workloads, capacities, operating models or imagery
outcomes. Imagery coverage is 10/149; the fixed 20-row/19-agreement blind review is incomplete.
Objective-completion and final-publication flags remain false.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch ninth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch ninth-reviewed --validate-only
```

## Fifty-site reviewed checkpoint

The [tenth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-tenth-reviewed/README.md)
adds Portus Munich MUC2, Meta El Paso, Meta Richland Parish and Microsoft Etobicoke. It
contains 150 physical sites, 153 projects, 41 countries, 104 non-US sites and 510 evidence
rows. This is 50 of the requested 100 additions, with 50 remaining. All 146 previous sites,
149 previous projects, 479 previous evidence rows and their GeoJSON features are preserved.
The public v0.17 release remains frozen at 100 sites.

Portus's May 28 release explicitly describes MUC2 being constructed on its existing Munich
campus. Financing and the expected Q1 2027 opening are not the physical evidence. The
operator explicitly groups MUC1 and MUC2; an operator-linked certificate names MUC1's
physical address at Marsstraße 5, Kirchheim. That address matches a community building
literally labelled Spacenet. Its point locates the shared campus only: no operator rename,
MUC2 footprint, transferred certification or building-use claim is inferred. The conflicting
operator pin 193 metres west remains excluded. The full relevant certificate page was
visually reviewed, including separate owner, Location, audit, issue and validity fields.

Meta El Paso retains the existing campus and project keys with the July 28 issuer statement
of current construction and an already-onsite workforce. City records corroborate the
Meta/Wurldwide campus north of Stan Roberts Sr. Avenue and west of U.S. Highway 54. The
community source explicitly marks its boundary very approximate; only its broad named-campus
point is selected. The rectangle is not a legal boundary, and a failed Census address query
does not become an official locator. TDLR's April 15 date is recorded as registration, not
publication or a physical observation. Financial ownership, future phases and capacity claims
remain unselected.

Meta Richland Parish retains its existing keys and Turner's July 16 observation of active
interior buildout in the first buildings. The operator names Turner as a contractor; Turner's
scope page separates Phase 1 delivery from Phase 2 preconstruction and future building works.
The named three-component community relation supplies only a whole-campus reference point.
Its northern component is not asserted to locate the first buildings, a legal entity's parcel
or Phase 2 construction. One campus is counted, not its phases, buildings or financial entities.
An independent second review checked both Meta status, identity and geometry chains.

Etobicoke's August 5 operator update describes an unfinished first building and continuing
installation work. Conflicting historical onset dates are preserved without selecting either.
The city's owner table explicitly links Microsoft to 48 Lowe's Place, while its July 22 motion
identifies the datacentre there. Pursuit of conditional occupancy is not granted occupancy or
operation. The unique municipal Land address point is checked against the same-ID official
EPSG:4326 response. Toronto's exact dataset page supplies the open licence despite the CKAN
catalogue's unspecified licence field. This point is not a building centroid, entrance or boundary.

Vaughan stays held: its licensed geometry cannot resolve the existing substantial-completion
scope conflict. The research packets also preserve named APAC construction leads with unclosed
source captures or exact locators, rather than reusing locality or nearby-facility points.
All selected points retain attribution, source-specific semantics and unknown accuracy. No
new roles, workloads, operating models, capacities or imagery results are inferred. Imagery
coverage is 10/153; the fixed 20-row/19-agreement blind review remains incomplete. Both objective
completion and final-publication flags remain false.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch tenth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch tenth-reviewed --validate-only
```

## Fifty-one-site reviewed checkpoint

The [eleventh reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-eleventh-reviewed/README.md)
adds Flexential Parker Compark Campus, retaining its existing unselected campus and project
keys. It contains 151 physical sites, 154 projects, 41 countries, 104 non-US sites and 518
evidence rows. This is 51 of the requested 100 additions, with 49 remaining. Every preceding
site, project, evidence row and GeoJSON feature is preserved. Public v0.17 stays at 100 sites.

The August 18 issuer disclosure explicitly names Denver-Parker as currently under construction.
The financing transaction, other planned developments, May permit issuance and March structural
completion are not used as fresh physical observations. Structural completion does not imply
the whole data center is finished. The bounded issuer successor check found no decisive
completion through August 20; absence from an index is not proof of no unreported event.

The Town's May permit report, full PDF page 2 row 18, explicitly binds Flexential DEN12 to
15255 Compark Boulevard and geographic record 223305207007. The county's exact street and
record match supplies Englewood 80112 as the postal name. This is not a transfer to Flexential's
separate Englewood operation. No lineage from the older parcel identifier ending 005 is invented.
The county coordinate and another county service's licence are not selected.

Census returns the exact official postal address once. The selected point is address-range
interpolation, not a building, entrance, legal parcel, campus centre or current-work extent.
The official FAQ's full relevant page was visually checked: the source datum is NAD83.
An independently repeated pyproj 3.8.0 / PROJ 9.8.1 transformation to WGS84 returns the same
numeric coordinates through NAD83 to WGS84 (1). Its reported 4-metre operation accuracy is
not site-locator accuracy; the latter remains unknown. Eight exact evidence bindings preserve
source hashes, attribution, identity, status, datum and completion-scope caveats.

New hold-only research preserves Vaasa's unclosed exact locator, APAC phase/date/identity gaps,
and Chesterfield's July county construction table. Existing labelled month-precision conventions
are recognized without changing the schema or inventing observation days. Chirisa's adjacent
CTP/DDC developments require conservative campus grouping. Peanut's exact parcel identity is
resolved, but reusable geometry remains unclosed; both Census queries altered the street to
Old Bermuda Hundred Road and were rejected. These research records add no sites.

No new roles, capacities, workloads, operating models or imagery outcomes are inferred.
Imagery coverage is 10/154 and the fixed 20-row/19-agreement blind review remains incomplete.
Objective completion and final-publication flags remain false.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch eleventh-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch eleventh-reviewed --validate-only
```

## Fifty-three-site reviewed checkpoint

The [twelfth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-twelfth-reviewed/README.md)
adds Flexential Hillsboro 5 on the Starr campus and Douglasville 2 on the North River campus.
It contains 153 physical sites, 156 projects, 41 countries, 104 non-US sites and 535 evidence
rows: 53 requested additions completed, 47 remaining. All 151 preceding sites, 154 projects,
518 evidence rows and GeoJSON features remain unchanged, as does the public v0.17 release.

Both projects use the August 18 issuer's explicit current-construction sentence, not the
financing transaction. Project identification is a documented analyst reconciliation. For H5,
the September 2025 owner release separates four operating facilities from named H5 under
construction; the May 2026 release gives its exact address and distinguishes H3 and future H6.
For D2, the May 2025 owner acquisition release identifies the 36 MW design at 1750 N River Road.
The July ESG release names H5 and D2 as awaiting completion, but within its FY2025 accomplishments
section: this is identity/completion-scope context, not a July physical observation.

The May releases and undated owner marketing use operational-sounding capability language.
That contrary context is retained. Full visual review of both H5 brochure pages found no dated
whole-project completion. The later explicit August work statement supports generic current
construction only; it does not establish that no part is operating or identify remaining halls.
Planned H6/Norcross developments do not inherit the current-build status. Bounded successor
checks found no decisive dated whole-project completion through August 20; index silence is
not proof that an unreported event never happened.

H5's 4975 NE Starr address matches named OSM way 1080170580, including operator and owner URL.
Its Nominatim representative point is independently checked inside the valid source ring.
Neighboring H4 objects with incorrect H5 website tags are excluded. The restricted municipal
point and the Census match for H3 are also unselected. Adjoining Starr facilities count once,
without merging other Hillsboro sites merely because they share a network.

D2's 1750 North River address matches named OSM way 1258702591 and its canonical owner URL.
Its representative point is likewise checked inside the valid source ring. The neighboring D1
object and Census interpolation near D1 are not selected. D2 is counted once, conservatively
reserving the adjoining North River facilities as one campus group. Its brochure was web-readable
but the raw request returned 403; no PDF hash, visual-review claim or evidence binding is invented.

Both points preserve ODbL attribution, WGS84 source coordinates and unknown positional accuracy.
Neither is a selected boundary, surveyed footprint, entrance or active-work extent. Seventeen
new source bindings are closed. Separate review-index evidence prevents new usage from changing
Parker's frozen evidence row. No new roles, capacities, workloads, operating models or imagery
outcomes are inferred. Imagery remains 10/156; the fixed 20-row/19-agreement blind review remains
incomplete. Objective-completion and final-publication flags remain false.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch twelfth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch twelfth-reviewed --validate-only
```

## Fifty-six-site reviewed checkpoint

The [thirteenth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-thirteenth-reviewed/README.md)
adds Google Bermuda Hundred, Chirisa Chesterfield Digital Drive and noris NBG6 Nürnberg Süd.
It contains 156 physical sites, 159 projects, 41 countries, 105 non-US sites and 562 evidence
rows: 56 requested additions completed, 44 remaining. All 153 preceding sites, 156 projects,
535 evidence rows and GeoJSON features remain unchanged. Public v0.17 remains byte-frozen.

The county's explicitly July 2026 table and visually reviewed full-page map identify three
Peanut buildings at 2100 Bermuda Hundred Road and two Digital Drive buildings at 1551 Digital
Drive as under construction. July 1 is the existing conservative month-start representation,
not an invented observation day or construction-start date. The whole stated month lies within
the fixed physical-observation window. Permit dates and PDF creation timestamps are unselected.

Peanut retains the prior unselected Google Bermuda Hundred stable identity. Reconciliation
uses the named county address and matching Bermuda Hundred water agreement, explicitly as
identity context rather than a normalized water metric. The December 2025 county planning
letter's visually reviewed page 4 binds the exact Peanut tax ID. All three buildings count once;
Old Bermuda, Upper Magnolia Green and Watkins Centre do not inherit this construction status.

Chirisa's Digital Drive development and adjoining CTP facilities count conservatively as one
physical campus. The operator's 2024 existing-campus expansion and 2025 combined-campus accounts
support that grouping despite today's separate marketing headings. Only Digital Drive's county
construction row is selected, not operating CTP halls. The existing Chirisa Lancaster site is
in Pennsylvania. Peanut and Digital Drive are distinct named properties approximately 2.82 km
apart, with independent addresses and parcel features; neither overlaps the preceding sites.

The exact Chesterfield parcel layer is covered by the open-data portal's full CC0 terms through
its public catalogue item `caac62a09b49446b8a20744963ba1d23`. The item links Cadastral_ProdA layer 3
and has an accuracy disclaimer, not a conflicting reuse restriction. The unlisted parent service
is not used as the rights bridge. Source-generated centroid responses explicitly request
EPSG:4326 and are copied as longitude/latitude, without street interpolation or local map tracing.
These are constituent-property reference points, not selected campus boundaries, construction
extents, entrances or surveyed coordinates. Positional accuracy remains unknown. Digital Drive's
Name and TaxID suffix discrepancy is preserved; the exact object, address and DDC owner provide
the binding. Its two clockwise exterior rings form a valid multipolygon for the independent
containment check; no source polygon is published. CC0 does not relicense county prose or imagery.

For noris, the original company post's August 13 timestamp dates explicit current concrete-shell
and elevator installation work. The separate mid-May and late-June IT-area deliveries and partial
cooling commissioning do not establish whole-phase operation. The August body does not literally
name NBG6 BA3: a documented analyst reconciliation joins the operator's exact code/campus post
with the award organizer's matching modular 400-square-metre description. The latter is identity
context, not a fresh construction observation or an operator-authored source.

The named NBG6 BA3 OSM way and unchanged Nominatim point agree, with independent ring containment.
BA1, BA2 and BA3 count once at Nürnberg Süd; headquarters and Slovak module fabrication add no
sites. The selected noris Schwalbach project is separate. The nearest preceding campus is MU4
roughly 146 km away; sampled polygon distances are only a duplicate-screening aid. ODbL
attribution, WGS84 and unknown accuracy remain explicit. This is a community constituent-building
campus locator, not an official address certification, boundary, work extent or imagery outcome.

Twenty-seven new bindings resolve to 25 unique selected raw captures, independently rehashed.
Cross-review found no admission blockers. Separate research keeps Vaasa, Mougins, Sify's named
Indian expansions and Federal Bank Kochi held for unresolved exact location or dated physical
work; financing, aggregate capacity and an undated ceremony cannot fill those gaps. No new roles,
capacities, workloads, operating models or imagery outcomes are inferred. Imagery remains 10/159;
the fixed 20-row/19-agreement blind review is incomplete. Both objective-completion and final-
publication flags remain false.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch thirteenth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch thirteenth-reviewed --validate-only
```

## Fifty-nine-site reviewed checkpoint

The [fourteenth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-fourteenth-reviewed/README.md)
adds Core Scientific Pecos Cottonwood, TeraWulf Lake Mariner CB-5 and CSC LUMI-AI Kajaani.
It contains 159 physical sites, 162 projects, 41 countries, 106 non-US sites and 589 evidence
rows: 59 requested additions completed, 41 remaining. Every preceding 156-site, 159-project
and 562-evidence row and GeoJSON feature is unchanged. Public v0.17 remains byte-frozen.

Pecos uses the original June 2 CEO post's explicit current vertical-construction statement.
The issuer leadership page links the exact author profile, and the April issuer release
corroborates the executive and existing-campus conversion identity. April milestones are
stale context, not refreshed work dates. The third-party July machine transcript is retained
only as contrary evidence: its completed-building answer is attributed to Adam Sullivan,
while its near-complete precast and future-shell answer is attributed to Matt Brown. Neither
is an audio-verified whole-HDC completion certificate. No new transcript lifecycle method
was added; only the existing authoritative physical-status method is selected.

The issuer's historical 1851 FM 2119 deed, named OSM relation 20669718 and unchanged Nominatim
point bind a genuine constituent of the operator-grouped Cottonwood 1 and 2 campus. Root and
independent review found the point inside its outer ring and outside the hole. The one-campus
locator does not identify the new hall or assert that both constituents are contiguous. The
existing unselected OSM facility identity is retained as a reference, not another count. The
older unselected Microsoft Pecos announcement has only locality-level geometry: its relationship
to Cottonwood remains unresolved, no separation is claimed and no Microsoft count is added.
Any later Microsoft admission must reconcile that relationship.

For Lake Mariner, the August 5 issuer update explicitly reports continuing CB-5 construction.
Delivered CB-3 and CB-4 commissioning do not supply CB-5 status. The May 2026 agreement defines
CB-5 at 7725 Lake Road, Barker, matching the single Census result exactly. PDF inspection of
the Census FAQ confirmed NAD83 and address-range interpolation. Independent pyproj 3.8.0 runs
of NAD83-to-WGS84 operation EPSG:1188 preserved the numeric coordinates. Its stated four-metre
transformation accuracy is not the unknown accuracy of the address interpolation. This point
locates the project's street address, not the physical building, entrance, parcel or campus
interior. Historical property evidence corroborates only the address. The existing Epoch campus
key is reused without importing modeled metrics, roles, geometry or lifecycle.

CSC's August 20 primary report states that the Kajaani expansion is under construction with
people currently working on site. This dates a current-work report, not the construction onset.
The March same-hall article and official Tehdaskatu 15 data-center address bind the community
building named CSC, alternative name LUMI. Its provider point lies inside the full source ring;
that ring is disjoint from the previously selected XTX Kajaani parcel. Existing LUMI and Roihu
operations count within one campus and do not complete the new expansion. March photographs
and future 2027 delivery are not selected physical observations. Initial capture start/end
timestamps remain explicitly unknown; response dates and file times are audit context only.

Both OSM locators retain ODbL attribution and WGS84 with unknown positional accuracy. They are
constituent-campus reference points, not official boundaries or active-work extents. Census
reuse guidance applies only to the federal geocoder facts, not the reserved issuer material.
All 156 prior identities and full selected geometries, plus the three new sites mutually, were
reviewed without a selected-cohort collision. Twenty-seven new bindings resolve to 26 unique
selected raw bodies; root and cross-review independently verified their hashes and byte counts.

The separate research packets keep DayOne Lahti, Cipher Black Pearl and Stingray held for exact
geometry. TATC and DDSP candidates lack qualifying dated physical work; Digital Halo's later
vendor post describes an April topping-out event, not new July construction. No roles,
capacities, workloads, operating models or imagery outcomes are inferred. Imagery remains
10/162; the fixed 20-project/19-agreement blind review remains incomplete. Objective completion
and final-publication flags remain false.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch fourteenth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch fourteenth-reviewed --validate-only
```

## Sixty-site reviewed checkpoint

The [fifteenth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-fifteenth-reviewed/README.md)
adds DayOne's Kiveriö campus in Lahti, Finland, preserving its original campus and project keys.
It contains 160 physical sites, 163 projects, 41 countries, 107 non-US sites and 597 evidence rows.
This is 60 of the requested 100 additions, with 40 remaining. All 159 preceding sites, 162 projects,
589 evidence rows and their full selected geometries are preserved. Earlier snapshots and the
public v0.17 release remain byte-frozen.

SRV's job 2984 bulletin reports current frame work on August 11 at Ilmarisentie 3. Its conflicting
week-32 label is retained, not silently corrected; the explicit date falls in ISO week 33. The
day-only date is normalized without inventing a publication time. End-August frame completion
and 2027 operation remain forecasts. September retrieval and older permit dates do not refresh
construction status.

Visual PDF review joins municipal permit 398-2025-418 at Väinämöisentie 2a to the October 2025
permit-register row at Ilmarisentie 3 through the exact same parcel 398-5-966-7. SRV and the city
independently identify DayOne in Kiveriö. DC-A, support buildings and possible later phases count
as one campus. The NLS cadastral WFS returns exactly one matching parcel and its own reference
point. Independent EPSG:3067-to-WGS84 conversion and containment checks agree; neither the point
nor its source parcel intersects any of the 159 prior selected features. This official reference
point is a campus locator, not a recomputed centroid, building footprint, surveyed entrance or
asserted complete campus boundary. Old road, wholesaler and regional-service coordinates remain
rejected. NLS's explicit CC BY 4.0 terms apply only to its data, with attribution and transformation
notice; the source point's positional accuracy remains unknown.

Eight new evidence bindings have independently verified raw-body hashes and byte counts. The
separate Google/Meta research packet preserves the Beaver Dam search-date conflict: the city
article and linked fact sheet are from November 2025, while the original July fire-department
account was inaccessible. Temple's July opening and Kuna's post-cutoff opening do not create new
construction observations. Asia's newly dated SMX01, Lanzhou and Ekibastuz leads remain held for
exact location, identity or classification checks. No held proposal changes the selected count.

No roles, capacities, workloads, operating models or imagery outcomes are inferred. Imagery
remains 10/163, and the fixed 20-project/19-agreement blind-review requirement remains incomplete.
Objective-completion and final-publication flags remain false.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch fifteenth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch fifteenth-reviewed --validate-only
```

## Sixty-one-site reviewed checkpoint

The [sixteenth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-sixteenth-reviewed/README.md)
adds the Monarch Compute Campus at Point Pleasant, West Virginia. It contains 161 physical sites,
164 projects, 41 countries, 107 non-US sites and 609 evidence rows: 61 requested additions completed,
39 remaining. Every preceding 160-site, 163-project and 597-evidence row and full selected feature
is unchanged. All earlier checkpoints and the public v0.17 release remain byte-frozen.

The July 14 WVDEP report documents actual land-disturbing work following July 11 rainfall and
requires a stop in one separate drainage area until controls are installed and agency compliance
is verified. July 14 is the current physical-state report date, not construction onset or a known
inspection day. The partial restriction remains unresolved; neither a whole-campus shutdown nor
clearance is inferred. Site preparation does not establish hall erection, IT installation or
delivered capacity. The bounded successor review found no whole-campus completion or cancellation
through the August 20 cutoff and does not claim exhaustive enforcement-record coverage.

The applicant's integrated power-and-three-data-center campus, agency application index, operator
page and project-participant disclosure support one campus identity. Visual review of application
pages 7, 93 and 221 preserves the distinction between its approximately 1100-acre application
and the broader 2250-acre marketed concept. Planned buildings and the power pad do not count as
additional sites. The quoted contiguous-or-adjacent regulatory definition does not independently
verify land contiguity. Linking the July enforcement report to this campus and exact stormwater
registration WVR113311 is explicit analyst reconciliation, not a permit number or street address
literally printed in that report.

The exact official Power Generation Pad South registration supplies the selected EPSG:4326 point.
Independent inverse projection of the same record's native EPSG:3857 point agrees. This checks
coordinate consistency, not survey accuracy; both point-placement method and positional accuracy
remain unknown. It is a constituent campus locator, not a data-center building, entrance, campus
centroid, work extent or property boundary. The distant M2 Pipeline record, Norway template
coordinate, datum-unstated application coordinate and conflicting 2027 notice are excluded.
The notice's Mason-versus-Monarch naming discrepancy is retained with its exact registration join.

Twelve new evidence bindings have independently verified raw hashes and byte counts. Root also
verified all 35 research capture hashes and reviewed all 160 prior selected identities and full
geometries, plus historical v97 aliases, without a selected-cohort collision. WVDEP's public GIS
context supports retaining only attributed isolated factual projections; its null licence
metadata is not relabelled as open-licensed or public domain. Source documents, maps and raw
GIS responses are not redistributed.

The separate Asia round-17 packet keeps SMX01 and Ekibastuz held for exact site location.
SM+'s issuer bulletin corroborates the executive's name and role but not the exact author-profile
link. The newly discovered valley website's dated news cards contain placeholder text, not
construction observations. Neither office pins nor generic power-station locations are selected.

No roles, capacities, workloads, operating models or imagery outcomes are inferred. Imagery
remains 10/164; the fixed 20-project/19-agreement blind-review requirement remains incomplete.
Objective-completion and final-publication flags remain false. At least 13 of the remaining
39 additions must be non-US to keep every country at or below 40 percent at the 200-site target.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch sixteenth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch sixteenth-reviewed --validate-only
```

## Sixty-two-site reviewed checkpoint

The [seventeenth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-seventeenth-reviewed/README.md)
adds Greenergy's Hüüru campus in Estonia. It contains 162 physical sites, 165 projects, 42 countries,
108 non-US sites and 618 evidence rows: 62 requested additions completed, 38 remaining. Every
preceding 161-site, 164-project and 609-evidence row and full selected feature is unchanged.
All earlier checkpoints and the public v0.17 release remain byte-frozen.

The July 30 MCF Group Estonia release explicitly reports that preparatory construction has begun.
Its issuer-supplied English translation is identified; the Estonian original was not inspected.
The selected status is conservatively site preparation, with July 30 as the report date, not a
known construction-start day. An independent reviewer found this stronger direct statement
while challenging the July 31 contractor's present-tense staffing wording. The owner describes
close to 200 workers as prospective peak staffing; that figure, the contract award, technical
delivery language and autumn forecast are not independent construction observations. The English
and Finnish contractor wording differences remain visible but neither supplies selected lifecycle.

The exact operator-labelled Office / Data Center address at Alajaama tee 1 matches OSM way
1043819046 by name, street number, postcode, website and phone. Root and independent review
reconstructed the exact ordered WGS84 enclosure and its representative point. Neither the point
nor the full source enclosure intersects any of the 161 prior selected features, and historical
alias checks found no represented Greenergy campus. This is a community-mapped campus locator,
not an official boundary, surveyed entrance, provider point or active-work extent. The source
node ids and ring are retained as ODbL-attributed derivation facts, not exported as an official
campus polygon. Positional accuracy remains unknown. A portable standard-library test independently
reproduces the point without depending on temporary raw captures or a GIS package.

The direct August 12 joint Greenergy/Tensor release still forecasts first deployment operation
later in 2026. It supplies successor context, not a new physical-work date. Already operating
halls and Nebius's planned deployment remain within this one campus and create no extra site.
The bounded review does not prove exhaustive absence of later completion or cancellation records.
The counsel page's JavaScript shell remains unselected. Nine selected source bindings and all
11 research captures have independently verified raw-body hashes and byte counts.

The separate Asia round-18 and Americas round-17/18 packets preserve explicit holds. Qingyang
has new work reporting but no exact accepted locator; MEL02's actual post is stale; Gangcheng's
May-only register and July building-specific fire filing need further review. Equinix's portfolio
expansion total does not refresh its old individual phase rows. AHI's new county locator route
does not close source authority or the legal-entity bridge. None of these holds changes the count.

No roles, capacities, workloads, operating models or imagery outcomes are inferred. Imagery
remains 10/165; the fixed 20-project/19-agreement blind-review requirement remains incomplete.
Objective-completion and final-publication flags remain false. At least 12 of the remaining
38 additions must be non-US to keep every country at or below 40 percent at the 200-site target.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch seventeenth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch seventeenth-reviewed --validate-only
```

## Round 19 research checkpoint: no additional admissions

The selected cohort remains 162 sites and 165 projects. Six research/locator packets preserve
the next evidence gates without creating another reviewed draft or changing frozen inputs.

The [Kenya locator review](../sources/research-expansion-200-africa-round19-nxtra-nbo1-locator-2026-09-09.json)
reproduces Nxtra's exact operator-authored Tatu City point and NB01/NBO1 alias link. This closes
the locator gate, not lifecycle. The [separate interview review](../sources/research-expansion-200-africa-round19-nxtra-2026-09-09.json)
binds the original podcast feed and a bounded local automated transcription; its executive
answer discusses future services, not physical progress. No acoustic certification or imagery
outcome is claimed. This checkpoint originally described the earlier CEO report as openly
syndicated. The [round 20 access correction](../sources/research-expansion-200-africa-round20-nxtra-nbo1-identity-review-2026-09-09.json)
withdraws that assumption: the preserved TNX response marks the relevant construction paragraph
inside an access-restricted body, and public rendered visibility was not established. That text
is not selected. The new public ITWeb report supports campus and event identity, not fresh
physical status. No universal verbatim-only rule is imposed. Prior research captures and frozen
core artifacts remain unchanged; no selected admission depended on this TNX assertion.

The [India review](../sources/research-expansion-200-india-round19-2026-09-09.json) preserves Rai's
existing-shell versus conversion versus future-greenfield distinction and adds a historical
government TP-1/SEZ identity record. Current physical-work meaning and the exact mapped-feature
bridge remain unresolved. The [Europe review](../sources/research-expansion-200-europe-round19-2026-09-09.json)
retains Alcalá's dated issuer construction statement but rejects the Cisneros substation parcel:
the government plan associates that infrastructure with Nabiax, not a Coravel campus locator.
The [Asia review](../sources/research-expansion-200-asia-round19-2026-09-09.json) keeps Qingyang's
unlocated project, STT Johor's financing-only update and Obayashi's unnamed construction trial held.

No roles, capacities, workloads, construction dates or sites are added. The 200-site goal remains
active with 38 sites outstanding; final-release imagery and blind-review gates remain open.

## Sixty-three-site reviewed checkpoint

The [eighteenth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-eighteenth-reviewed/README.md)
adds one Aligned Conesville CMH-02 campus in Ohio. It contains 163 physical sites, 166 projects,
42 countries, 108 non-US sites and 629 evidence rows: 63 requested additions completed, 37 remaining.
Every preceding 162-site, 165-project and 618-evidence row and full selected feature is unchanged.
All earlier checkpoints and the public v0.17 release remain byte-frozen.

The [Conesville review](../sources/research-expansion-200-americas-round20-conesville-2026-09-09.json)
preserves the contractor's actual pad-earthworks completion in July 2026. Root and independent
review accepted this as site preparation, not completion or operation of the entire campus and
not proof of continuing August work. The entire July interval falls inside the fixed observation
window. July 1 is the existing conservative month-start representation, not an asserted exact
work day. The page's June initial publication and August 24 modification do not date that work.
The frozen proposal's pending-review labels record its pre-admission state; this checkpoint's
explicit contract and independently pinned acceptances record the subsequent root decision.

The locator is the county-computed centroid of one exact Aligned-owned constituent parcel,
0100000080609 / OBJECTID 27692. County minutes, the county-linked viewer and its underlying parcel
service close the identity and source-authority chain. The explicit EPSG:4326 output with datum
operation 1188 independently reproduces the native EPSG:3734 centroid to about 0.00011 metres;
that numerical agreement is not positional accuracy. The selected point is inside the parcel,
not a whole-campus centroid, boundary, entrance, building or active-work footprint. The operator
map marker lies outside the five Aligned-owned county features and is rejected, as are the
county's inconsistent stored latitude/longitude attributes. No intersection or prior identity
match was found against all 162 preceding full geometries and physical keys.

CCU's contractor report names Aligned and Conesville but not CMH-02 or a parcel. Its association
with the operator-named campus and official Propco parcel is explicitly analyst reconciliation.
Pads, buildings and future phases remain one campus. Bounded primary successor checks found no
whole-campus completion or cancellation; generic operator marketing and contradictory secondary
directory labels do not establish one. Eleven selected bindings and all 38 research captures
have independently verified raw-body hashes and byte counts. Only one isolated official point
and compact attributed facts are redistributed, not the county polygon, media, raw sources or
substantive source prose. Empty county licenceInfo is not an open licence; accuracy stays unknown.

Round 20 also preserves the next gates without admitting additional sites:

- The [Asia review](../sources/research-expansion-200-asia20-2026-09-09.json) verifies Techno's
  August 12 current-build statement for its RailTel Noida project. An official RFP supplies a
  B-209 plot midpoint but no coordinate datum; the final award-to-plot bridge is also unresolved.
  Neither a WGS84 point nor an exact parcel association is invented. Its smaller live phase
  remains distinct from the current build within one campus.
- The [Kolkata locator review](../sources/research-expansion-200-india-round20-kolkata-locator-2026-09-09.json)
  preserves a current foundation/piling statement but cannot bind the exact mapped plot to the
  issuer. A similarly named allotment applicant is not assumed to be the same legal entity, and
  unreferenced map graphics do not become coordinates.
- The [Nairobi identity/access review](../sources/research-expansion-200-africa-round20-nxtra-nbo1-identity-review-2026-09-09.json)
  corrects the earlier TNX public-access assumption. The new public ITWeb article supplies event
  and campus identity, not fresh physical work. The [executive authority review](../sources/research-expansion-200-africa-round20-authority-2026-09-09.json)
  retains incomplete public-source attribution checks without promoting an appointment preview
  or changing a managing-director title into CEO. Earlier denied or restricted routes stay closed.
- The [Europe review](../sources/research-expansion-200-europe-round20-2026-09-09.json) separates
  NTT Berlin's scheduled summer start, stale YEXIO groundbreakings, and nearby Herne roadworks
  from qualifying current data-center construction. None adds a site.

No roles, capacities, workloads, operating models or imagery outcomes are inferred. Imagery
remains 10/166; the fixed 20-project/19-agreement blind-review requirement remains incomplete.
Objective-completion and final-publication flags remain false. At least 12 of the remaining
37 additions must be non-US to keep every country at or below 40 percent at the 200-site target.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch eighteenth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch eighteenth-reviewed --validate-only
```

## Nineteenth reviewed partial draft

The [nineteenth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-nineteenth-reviewed/README.md)
adds Procergs Porto Alegre, limited to new substation construction at its existing data-center
campus. It contains 164 physical sites, 167 projects, 42 countries, 109 non-US sites and 639
evidence rows: 64 requested additions completed, 36 remaining. Every preceding selected row,
full site feature, source binding and raw-input hash is preserved. The public v0.17 remains frozen.

Contract SHA-256: `29bc6728271040a949a39bb815296ec3c760e3ee5a506ef3c1fd8d035a0b0e0b`.
Manifest SHA-256: `8f02039a76ad8e4872f924d36749c7f536738252035e5389c60ea6e0075d950c`.

The [Americas review](../sources/research-expansion-200-americas-round21-2026-09-09.json)
binds the owner's July physical-progress report, item I.b, to contract 6033-00. July 1 is only
the existing conservative month-start representation of the explicitly reported July status;
it is not an invented observation or construction-start day. The report's repeated comparison
heading and July-to-August table footer remain disclosed template inconsistencies. Spending
percentages, completed recovery work, purchased storage and future deliveries do not supply
additional physical projects or dates. The August 17 original interview distinguishes rebuilt
existing halls from electrical renewal still expected in September, not completed at cutoff.

The public contract template identifies the new substation beside Procergs' headquarters;
a separate official tender explicitly identifies its data center at that same address. The
template is identity evidence, not a signed award or work observation. The exact OSM building's
short name, historic company name and canonical website close the community-feature association.
Its provider-supplied Nominatim point and full ring were checked against all 163 predecessor
geometries, with no intersection or alias collision. Differing street and district labels remain
explicit. The point locates the campus, not the new substation footprint, entrance, parcel or
surveyed position. Accuracy is unknown. OSM data retain ODbL attribution and rights; third-party
PDFs, media, code and raw HTML are not redistributed. Root and independent reviewer verified all
ten selected complete capture hashes, source bindings, relevant PDF pages and scope separation.

New round 21 holds preserve the next exact gates:

- [Ōme, Japan](../sources/research-expansion-200-asia-round21-2026-09-09.json): current construction
  exists, but the precise parcel is absent from the inspected public-coordinate dataset;
  successor review and publisher reuse/access questions remain unresolved.
- [Türksat Gölbaşı](../sources/research-expansion-200-mena-round21-2026-09-09.json): July 22 physical
  work is supported, but the specific construction-campus-to-headquarters-marker bridge is not.
- [Telehouse West Two](../sources/research-expansion-200-europe-round21-telehouse-2026-09-09.json):
  month precision need not block July status, but reuse terms and live locator access do. The
  supposed SCR download returned unavailable-consultation HTML, not a verified PDF capture.
- [Vösendorf](../sources/research-expansion-200-europe-round21-voesendorf-locator-2026-09-09.json):
  the [identity review](../sources/research-expansion-200-europe-round21-voesendorf-identity-2026-09-09.json)
  binds August 13 municipal construction and Microsoft's site board for further review. The
  municipality does not name Microsoft; the association is geographic reconciliation. A wrong
  southern construction feature, an imprecise unnamed greenfield and street bounds are excluded.
  A project-bound parcel or another exact reusable locator is still needed.
- Terranova Campinas remains held for its exact locator; TRU Hillside for a fresh dated physical
  observation. Neither adds a selected site.

No new roles, metrics, workloads, operating models or imagery reviews are inferred. Imagery is
10/167, and the fixed 20-project/19-agreement blind review remains incomplete. Both completion
and final-publication flags remain false. At least 11 of the remaining 36 additions must be
non-US to keep every country at or below 40 percent at 200 sites.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch nineteenth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch nineteenth-reviewed --validate-only
```

## Twentieth reviewed partial draft

The [twentieth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-twentieth-reviewed/README.md)
adds Bulk N01 in Vennesla, Norway, and Bulk DK01 in Esbjerg, Denmark. It contains 166 physical
sites, 169 projects, 42 countries, 111 non-US sites and 650 evidence rows: 66 requested additions
completed, 34 remaining. All preceding rows, full features, source bindings and raw-input hashes
remain unchanged. Public v0.17 and every earlier checkpoint remain frozen.

Contract SHA-256: `790a7784f3884162d0fad611d0bfc12ae241114654c3dd7f7dcadd458163a1c6`.
Manifest SHA-256: `f07af48c36f96278e41cc8a1aead764d5b5e2538f71e1020aec96b9be2da8c84`.

The [Bulk round 22 review](../sources/research-expansion-200-europe-round22-2026-09-09.json)
binds the operator's Q2 report to ongoing new-facility construction and plot preparation at N01,
and the new building and power connection at DK01. June 30 is the reporting-period observation;
July 16 is the corroborated report publication, not work onset. Existing operating halls are not
assigned the new-work lifecycle. No named DCM phase, capacity, role, tenant, workload or operating
model is inferred. OSIX's inclusion in an aggregate headline, Arendal land acquisition and the
separate industrial-property portfolio do not supply additional physical sites.

Each operator page publishes its own campus URL, address and literal decimal point together in
one JSON-LD object. Although its name field is generic, the site URL and address distinguish the
campus from Bulk's Oslo corporate footer. Schema.org's GeoCoordinates definition supplies WGS84
semantics. The Danish government facility record independently matches DK01's address. N01's
named community polygon contains the primary point, but is not promoted to an official boundary;
the older brochure's different DMS locator has no explicit datum and remains unselected. Full
geometry comparisons against all 164 prior sites found no intersection: nearest prior sites are
130.15 km from N01 and 6.11 km from DK01. The new campuses are 308.25 km apart. These are campus
locators, not construction footprints, surveyed entrances or quantified accuracy claims.

Root and independent review checked the exact capture hashes, relevant full PDF pages, source
associations, coordinate semantics and spatial separation. Only compact attributed facts are
retained; no open licence is asserted for Bulk content, and OSM audit facts retain separate ODbL
attribution. Raw documents, media and HTML stay temporary and unredistributed. The failed Jorton
HTTP 455 request has no saved body or evidence hash and was not retried or selected.

Round 22 holds remain outside the draft:

- [SoftBank Tomakomai](../sources/research-expansion-200-asia-round22-2026-09-09.json): new
  authoritative construction testimony, but no accepted exact campus locator. Missing parcel
  bridge and unresolved public-map location warnings are preserved; no warning filters bypassed.
- [Terranova Campinas](../sources/research-expansion-200-americas-round22-terranova-2026-09-09.json):
  exact primary parcel identity, but geometry, CRS and reuse remain unresolved. A post-cutoff
  suspension request is not recast as an executed stop or pre-cutoff cancellation.
- [ACE Gabon Carrier Hotel](../sources/research-expansion-200-africa-round22-2026-09-09.json):
  fresh ministry construction report, but contrary landing-station location labels remain
  unresolved. A different completed ST Digital facility is not treated as an ACE successor.

Imagery remains 10/169 and the fixed 20-project/19-agreement blind review remains incomplete.
Completion and final-publication flags remain false. At least 9 of the remaining 34 additions
must be non-US to keep every country at or below 40 percent at 200 sites.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch twentieth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch twentieth-reviewed --validate-only
```

## Twenty-first reviewed partial draft

The [twenty-first reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-twenty-first-reviewed/README.md)
adds DataOne Vineland's Phase 2 building on one physical campus. It contains 167 sites,
170 projects, 42 countries, 111 non-US sites and 666 evidence rows: 67 requested additions,
33 remaining. All preceding rows, full features, source bindings and input hashes remain
unchanged. Public v0.17 and every earlier checkpoint remain frozen.

Contract SHA-256: `a13e0fdffce1d12a2c1f602fb84ef5c7b1b1efeb90e222e18e44ba3f7d9c8a8d`.
Manifest SHA-256: `43a353490c13d1cb347c1ad963f12d7495df41918bc412484bb2efceb07cb2fb`.

The [status and successor review](../sources/research-expansion-200-us-round23-dataone-vineland-2026-09-09.json)
binds the city's newly issued August 7 notice to its explicit current-construction statement
for the Phase 2 datacenter building. August 17 is a scheduled hearing, not the physical date.
The original campus and Phase 2 project identities are retained; Phase 1 and ancillary
equipment do not create extra sites, roles, workloads or capacity observations.

The complete signed August 6 LNG and August 10 Bloom Energy stop-work orders were visually
inspected. Both check the generic All Construction box but expressly qualify the stopped work
to their named equipment. Those equipment scopes are not selected. The scans also correct
reversed equipment dates in one host article and faulty OCR address digits. Later site-plan
approval is not treated as construction-permit clearance or verified rescission of the orders.
Undated December 2026 and 2027 delivery forecasts and generator use do not prove completed
Phase 2 construction or operating status. No imagery outcome is inferred from document scans.

The [independent geometry review](../sources/research-expansion-200-us-round23-dataone-vineland-geometry-2026-09-09.json)
matches municipal Block 7503 Lot 35.01, DataOne Vineland LLC and 3963 South Lincoln Avenue.
The one public parcel ring is returned in WGS84 using explicit transformation 1188 from
EPSG:3424; root independently reproduced every vertex and the full-geometry comparison against
all 166 prior sites. No intersection was found; the nearest prior site is Amazon Falls Township,
83.39 km away. The mapped parcel is a campus locator, not a surveyed or complete campus boundary,
new-building footprint or active-work extent. Its display anchor is derived; undocumented
geographic-looking coordinate attributes and old Lot 33.01 are not selected.

Only isolated attributed parcel and source facts are retained. The city provides no open licence
or quantified accuracy; its disclaimer and disabled export-widget setting are preserved.
The ordinary public one-record query was used without changing controls or exporting a bulk
dataset. Raw maps, HTML, PDF, scans, signatures and other publisher media remain unredistributed.

Round 23 [Aurora](../sources/research-expansion-200-americas-round23-aurora-2026-09-09.json)
and [six non-US screens](../sources/research-expansion-200-nonus-round23-2026-09-09.json) remain
outside the checkpoint. Aurora's exact city locators do not date its inspections; the original
photographer's caption has not been accepted as the authoritative physical-status source.
Non-US leads retain stale, forecast-only, agreement-only or unavailable-source findings.

Imagery remains 10/170, and the fixed 20-project/19-agreement blind review remains incomplete.
Completion and final-publication flags remain false. At least 9 of the remaining 33 additions
must be non-US to keep every country at or below 40 percent at 200 sites.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-first-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-first-reviewed --validate-only
```

## Twenty-second reviewed partial draft

The [twenty-second reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-twenty-second-reviewed/README.md)
adds Daou Jukjeon, Digital Park Fechenheim and QTS Aurora DEN1. It contains 170 sites,
173 projects, 42 countries, 113 non-US sites and 693 evidence rows: 70 requested additions,
30 remaining. All preceding rows, full features, source bindings and input hashes remain
unchanged. Public v0.17 and every earlier checkpoint remain frozen.

Contract SHA-256: `1c034319c5fc05bc6d3ae499b391bf2c4e3e4bb20ef8046974651bffab1ea5a4`.
Manifest SHA-256: `29796493c50a747982ba8d8f3709606c8c4d0280ac7c2c9686783a5696e0fd24`.

[Daou Jukjeon](../sources/research-expansion-200-asia-round24-2026-09-09.json) selects the
August 14 issuer filing's explicit current-build narrative. June 30 is the financial period end,
not an invented site inspection date. Complete PDF pages 4, 29 and 30 were independently
visually reviewed, including the contrast with already operating centers. The exact named
operator marker identifies one campus across lots 23-11/12/13 in Jukjeon-dong, Yongin.
Its explicit Google LatLng convention establishes WGS84; the linked Google place coordinate,
headquarters address and post-cutoff-created presentation are not selected. Generic construction
does not establish a particular MEP stage, power capacity or operational workload.

[Digital Park Fechenheim](../sources/research-expansion-200-europe-round24-2026-09-09.json)
selects UW04 constituent-substation construction only. Lupp's July 2 public account describes
the building as being built and current execution following a mid-June groundbreaking.
The August 11 modification and absence of a July 2 snapshot remain explicit. Neither a finer
groundbreaking day nor completion of the listed excavation/foundation scope is asserted.
The new project keeps the existing unselected FRA20 campus key. Digital Realty explicitly
places FRA20 on the same campus; its named facility point is a campus locator, not UW04's
footprint or street address. The current frontend runtime binds the coordinate and CRS trace.
Existing FRA18 operations, the stale FRA20 building observation and UW03 are not selected.

[QTS Aurora DEN1](../sources/research-expansion-200-americas-round24-2026-09-09.json) resolves
the earlier hold through a genuinely new public municipal inspection route. The successful
August 19 drywall inspection identifies actual first-layer wall work in two DC2 data-hall zones.
Permit serial/type, property 227490 and 1140 N Gun Club Road reconcile the inspection, city permit,
document index and exact city address point. Cancelled insulation and wrongly requested framing
inspections are excluded; they are not campus cancellation. Completed DC1 and separately permitted
DC3 count neither as selected projects nor extra sites. September inspections are successor context,
not an August status refresh. No restricted QTS operator-page content is used.

Root independently verified all 27 selected raw-evidence hashes and byte counts, the critical
identity records, and all three new points against the full 167 predecessor geometries and
each other. There are no intersections or shared-campus identities. Aurora's explicit
EPSG:2232-to-WGS84 operation 1188 was independently reproduced; transform-operation accuracy is
not source-point accuracy. All locators retain unknown positional accuracy and campus-only scope.
Only isolated attributed factual projections are retained, with publisher copyright and the
city's disclaimer/risk/indemnity terms explicit; no broad open-data licence is inferred.
Raw source documents, HTML, maps, images, source code and personal inspection names are not
redistributed. Google documentation's separate licence does not license operator or map data.

[Root-lane holds](../sources/research-expansion-200-us-round24-holds-2026-09-09.json) preserve
Soluna Kati's promising physical evidence and September 8 post-cutoff completion, but no exact
campus locator. Conflicting directory addresses and the wind-farm point are not substitutes.
The unsafe county-document redirect and restrictive appraisal-search terms were respected.
Richmond RCH-1 retains an edited-post date/access gap; its brochure is not a physical-work report.
Prime's May 7/21 groundbreaking reports remain outside the window. Freestone and Turksat retain
unresolved identity bridges. The Asia packet also preserves Naver Sejong and GS Goyang holds.

Imagery remains 10/173, and the fixed 20-project/19-agreement blind review remains incomplete.
Completion and final-publication flags remain false. At least 7 of the remaining 30 additions
must be non-US to keep every country at or below 40 percent at 200 sites.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-second-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-second-reviewed --validate-only
```

## Twenty-third reviewed partial draft

The [twenty-third reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-twenty-third-reviewed/README.md)
adds DigiCo SYD1 Ultimo. It contains 171 sites, 174 projects, 42 countries, 114 non-US sites
and 704 evidence rows: 71 requested additions, 29 remaining. Every preceding row, full feature,
source binding and input hash remains unchanged. Public v0.17 and all earlier drafts stay frozen.

Contract SHA-256: `0b85ec5fb8bc3c7644f419d21d62fcf5a7ee811226d0c48c0312117b9bee622a`.
Manifest SHA-256: `b5cbe82e4ae1fce7aff98f2cff4344ec90cf2015a91b10df96ec134cd0ea3783`.

[DigiCo's review](../sources/research-expansion-200-asia-round25-2026-09-09.json) selects
only preparatory works reported by SHAPE's CEO during the August 19 results call. Public
transcript segment 27 describes work already being performed; the preceding answer separates
it from the handed-over first stage. The issuer's presentation independently names SYD1 Ultimo
and the existing two-building campus, and its annual report confirms the speaker's executive
role. Early-contractor involvement alone is not selected as physical work, and no main contract,
specific trade or structural milestone is inferred. The third-party transcription is not
audio-verified. Only public preview segments 1-31 are used: segments 32-62 are actually hidden
by the publisher's access controls, not an available full-call source. They are excluded.

The August 21 operator presentation distinguishes completed 20 MW from the next 52 MW expansion
within the full 88 MW programme. It corroborates the distinction between design/ECI and early
physical works, but does not independently establish a pre-cutoff observation. These numbers
are phase-identification context only, not normalized capacity. The completed upgrade, Sydney
East/West buildings and future phases count as one physical campus and one selected project.

The exact NSW Planning Portal feature binds application SSD-69637456 and entity 75575896 to
the named expansion. Its unchanged point `[151.197, -33.875]` is published to only three decimal
places: a coarse campus reference, potentially outside building footprints, not a surveyed
point, entrance, parcel, boundary or exact work area. Accuracy remains unknown. The architect
independently binds the East/West campus to 400 Harris Street. Root reproduced the exact
GeoJSON feature, all 11 source hashes/byte counts and 15 short byte anchors, then compared
the point against all 170 prior full geometries. No intersection or shared-campus identity
was found; the nearest prior geometry is Goodman SYD01 Artarmon, approximately 6.32 km away.
Other operators' SYD1 codes are not an identity match.

Department-produced metadata retains its scoped CC BY 4.0 attribution; that licence does not
cover applicant plans, third-party submissions or Google map content. Other sources retain
their reserved copyright and separately reviewed terms. Only isolated attributed factual
projections are redistributed, not raw HTML, complete transcripts, source code, PDFs, plans,
photos, personal contacts or map data. The denied OSM feature is not used or accessed by an
alternate route. No roles, workloads, power metrics or independent imagery outcomes are added.

The [root-lane holds](../sources/research-expansion-200-root-round25-holds-2026-09-09.json)
and [Pima follow-up](../sources/research-expansion-200-americas-round25-pima-followup-2026-09-09.json)
keep Project Blue excluded: its May 22 memo summarizes a May 15 contractor response about
May 8-14 work and remediation, not a fresh May 22 inspection. The public tracker covers only
adjacent business days; the denied DEQ route was stopped. Novva Mesa, Cyta RedMax, DDC307,
PAIX and Hassan Allam remain announcement, acquisition, contract or stale-status holds.
[Kati's new issuer schematic](../sources/research-expansion-200-americas-round25-2026-09-09.json)
lacks a geographic reference and cannot locate the campus. September 8 completion is not
backdated, and no wind-farm or conflicting directory point is substituted.

[European round 25](../sources/research-expansion-200-europe-round25-2026-09-09.json) preserves
HLRS III's post-cutoff August 27 physical report, Leopoldsdorf's prospective 2027 start and
Lefdal's transaction-only update; the denied Ada source remains unused.
[Two further European screens](../sources/research-expansion-200-europe-round25b-2026-09-09.json)
retain TTC's historical retrospective and Polcom's 2024 forecast as holds. The Asia packet
also excludes NTT Ota's post-cutoff announcement and holds GreenSquare's ambiguously dated work.
Root rechecked 13 raw captures across the separate root, Americas and European hold packets.

Imagery remains 10/174 and the fixed 20-project/19-agreement blind review remains incomplete.
Completion and final-publication flags remain false. At least 6 of the remaining 29 additions
must be non-US to keep every country at or below 40 percent at 200 sites.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-third-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-third-reviewed --validate-only
```

## Seventy-three-site reviewed checkpoint

The [twenty-fourth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-twenty-fourth-reviewed/README.md)
adds Cloud4Y Marfino and OMNIA Pecém. It contains 173 physical sites, 176 projects, 43 countries,
116 non-US sites and 722 evidence rows. This is 73 of the requested 100 additions, with 27 remaining.
Every preceding CSV row, full site feature and evidence record remains unchanged. The public
v0.17 release and all earlier draft snapshots remain byte-frozen.

Marfino selects June construction of the main data-center building and its first-phase supporting
works. The July 13 corporate report explicitly covers June: June 1 is a conservative month-start
representation of the June 1-30 interval, not an exact inspection or first-concrete day. Concrete
had been placed in energy-center piles; pads and slabs remained future work. The already operating
container center and later planned modules are excluded. Cloud4Y's own facility page endorses the
exact Habr corporate-blog namespace. Its current Cloud4U display label does not establish a legal
rename date. The operator's Marfino contact card supplies the exact campus point; the linked click
handler and Yandex API defaults resolve misleading latitude/longitude attribute names. This is a
campus reference point with unknown positional accuracy, not a building footprint or parcel.

Pecém selects the June 16 official port/Casa Civil report's named OMNIA construction visit, not the
separate railway and logistics-terminal work in the same article. SEMACE's named project record
for enterprise 127774 provides the exact campus marker. The signed installation license and live
service share the corporate identifier and process number, connecting the historical CDV DC I name
to current OMNIA BR PC 01 without inventing a rename date. The substantive project location is
Caucaia; the license holder's Maracanaú office is excluded. The original stable keys remain, while
the new expansion display label makes no additional TikTok/ByteDance tenant claim.

Pecém's public map passes the literal latitude/longitude fields to a WGS84 interface. The original
applicant survey datum and measurement accuracy remain unknown. The signed license's transposed
UTM N/E suffixes are retained as a source caveat; neither a corrected boundary nor the interpreted
permit polygon is selected. Off-site transmission, construction-camp, road and forest-credit
markers are not campus substitutes. All 32 public company licensing records were inspected for
completion/cancellation context. Administrative validity is not physical construction evidence or
proof of compliance; the earlier MPF/DPU recommendation remains explicit unresolved regulatory
context, not an established judicial construction injunction.

Both points were independently compared with all 171 preceding full geometries and each other,
including polygon holes. No overlap was found. Approximate nearest-site screening distances are
782 km from Marfino to Telia Vilnius and 41.79 km from Pecém to Scala Praia do Futuro; these are
duplicate-screening measurements, not coordinate-accuracy estimates. Only isolated attributed
coordinate facts and compact restated source facts are redistributed. No open license is inferred
for operator material, SEMACE collections, source code, PDFs, photographs or provider maps.

The [root hold record](../sources/research-expansion-200-root-round26-holds-2026-09-09.json) preserves
Bolshaya Tsifra's July work report and its unresolved building-to-coordinate match. Generic house
number 16 is not substituted for building 1. Separate regional records retain Rongtai's remaining
geometry/successor gap, Romford's delivered-expansion evidence and Campus Oulu's ambiguous agreement
wording. These research records do not increase the count.

The checkpoint binds 486 source selections and 73 accepted additions. No new roles, workloads,
power metrics, certifications or imagery reviews are inferred. Imagery coverage is still 10/176;
blind review remains a fixed 20-row sample requiring 19 agreements from the expanded population.
The 200-site objective and final-publication gates remain incomplete.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-fourth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-fourth-reviewed --validate-only
```

## Round 27 research checkpoint: count unchanged

The cohort remains 173 physical sites, 176 projects and 722 evidence rows. No candidate in this
round closes every admission gate, and no frozen record or generated release is changed.

The [Key Point locator review](../sources/research-expansion-200-europe-round27-keypoint-spb-dc2-2026-09-09.json)
closes an operator-published St Petersburg campus point, with documented provider axis order,
unknown positional accuracy and comparison against all 173 full geometries. The separate
[lifecycle review](../sources/research-expansion-200-root-round27-keypoint-lifecycle-2026-09-09.json)
holds admission: June forum coverage and a July contractor interview describe active project
implementation but do not unambiguously establish current physical work. The undated construction
label, old start announcement and permit do not fill that gap.

The [Shoham investigation](../sources/research-expansion-200-root-round27-shoham-2026-09-09.json)
finds that an official permit assigns the tempting Rakefet 4 address to Amazon, not an established
MultiDC location. Kardan's newer annual report retains the 27.4-dunam campus description without
an exact locator. MultiDC's existing July physical-work evidence remains held for geometry.

The [San Bovio audit](../sources/research-expansion-200-europe-round27-2026-09-09.json) resolves an
apparent source conflict: the complete current updates retain preliminary site activity, compatible
with the baseline's narrow `site_preparation` selection. September principal works remain a forecast.
The original July raw body was not independently recovered; that limitation remains explicit.

[Asia](../sources/research-expansion-200-asia-round27-2026-09-09.json) retains Qingyang's July outdoor
work with unresolved geometry, Huwei's ceremony/forecast distinction and MiTASUN's limited public
interview scope. [Americas](../sources/research-expansion-200-americas-round27-2026-09-09.json)
preserves the earlier Fox Creek power-plant/data-center distinction, Hawesville's conflicting issuer
wording and Los Teros's missing fresh authoritative observation. Denied routes remain stopped.

There are 27 additions remaining; at least four must be non-US to satisfy the 40-percent country
ceiling at 200 sites. Imagery remains 10/176, blind review remains incomplete, and neither the
200-site objective nor final-release readiness is complete.

## Seventy-five-site reviewed checkpoint

The [twenty-fifth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-twenty-fifth-reviewed/README.md)
adds DC BLOX Palm Coast and envia TEL's shared Datacenter Campus Leipzig. It contains
175 physical sites, 178 projects, 43 countries, 117 non-US sites and 744 evidence rows.
All 173 preceding sites, project rows and evidence rows remain unchanged. This is 75 of the
requested 100 additions; 25 remain, at least three of which must be non-US under the country ceiling.

Palm Coast's June 19 municipal clarification explicitly reports current construction of one
approved building. The city's project hub identifies colocation capabilities, so the selected
scope is a cable landing station with colocation, not an inferred hyperscale or AI facility.
The proposed second building is excluded. The older approved plan's 34,875-square-foot total
differs from the current statement's 33,760 square feet; the source/version discrepancy is retained
without inventing its cause or selecting a normalized area metric.

The city links that plan under 1109 Town Center Boulevard. Its Lot 7B and older 1035/0070 parent
labels are reconciled against the current exact address object and parcel 0071, not promoted to
separate sites. The municipal point is queried in the address layer's stored EPSG:2881
NAD83(HARN) CRS and converted through the preserved HARN-to-WGS84 operation. The service's
EPSG:2236 response is a different coordinate route, not the stored CRS. That earlier route and
the server's WGS84 result remain explicitly unselected audits. The selected operation's one-metre
accuracy is not source-feature accuracy; the campus point's actual accuracy remains unknown.
The point is not a parcel boundary, entrance or exact construction footprint. Public GIS access
and AS-IS scale warnings are not treated as an open-license grant; only isolated attributed facts
and the numeric locator are redistributed, not the plan, source polygons or media.

Leipzig's May 27 operator report distinguishes the ongoing fourth section in Leipzig 2 from
the already operating first three sections. Datacenters 1 and 2 are expressly grouped as one
campus. The contemporaneous status is not taken from the 2025 financial period, spring opening,
network rollout or later retrieval. First-party event and directions pages bind Leipzig II to
Leipziger Straße 116a in Taucha. The exact-address OSM building's literal Nominatim centroid
locates the shared campus through that constituent only. It is not the fourth-section footprint,
an official survey, the 116b office or the alternative navigation entrance. OSM contributor
attribution and ODbL data rights remain separate from the operator's reserved-content rights.

Both points were independently compared with all 173 full preceding geometries, including
polygon holes, and each other. Palm Coast's complete source parcel was also screened; no overlap
was found. Bounded city follow-up and operator-index successor checks found no authoritative
completion/cancellation of the selected projects before August 20. This is not an exhaustive
absence claim and does not advance the lifecycle reference date.

The [Magadan hold](../sources/research-expansion-200-root-round28-magadan-2026-09-09.json) preserves
July physical-work reporting without substituting a settlement, legal office, offsite substation
or sanitary-zone polygon for campus geometry. [Asia's hold record](../sources/research-expansion-200-asia-round28-2026-09-09.json)
retains VNET Ulanqab Phase II's recent contractor report and unresolved relationship to the older
Bayin campus, plus Gimpo's fresh-secondary/stale-primary distinction.
[Conapto and Pyhäjoki](../sources/research-expansion-200-europe-round28-2026-09-09.json) remain
temporal-evidence holds; the Finnish headline/body tension is not silently resolved into a precise
start day. These records do not add to the accepted count.

The cumulative contract binds 508 source selections and 75 additions. No new roles, workloads,
power metrics, certifications or imagery reviews are inferred. Imagery remains 10/178, and blind
review remains a fixed 20-row sample requiring 19 agreements from the expanded population.
The 200-site objective and final-publication gates remain incomplete.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-fifth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-fifth-reviewed --validate-only
```

## Seventy-six-site reviewed checkpoint

The [twenty-sixth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-twenty-sixth-reviewed/README.md)
adds one DataBank Red Oak campus. It contains 176 physical sites, 179 projects, 43 countries,
117 non-US sites and 757 evidence rows. The cumulative contract binds 521 source selections.
All 175 preceding sites, project rows and evidence rows remain unchanged.
This is 76 of the requested 100 additions; 24 remain, at least three of which must be non-US
under the country ceiling. The public v0.17 release and every earlier checkpoint remain frozen.

DataBank's July 26 company report describes actual current construction across its first phase.
The selected project is therefore `curated:databank-red-oak-campus:first-phase-current-build`,
not a newly dated assertion for each of DFW9 through DFW12. The existing campus key is preserved;
the older individual-building research rows remain unselected and unchanged. The source's July 29
metadata edit and September retrieval do not advance the July 26 current-status report date.
DFW9's expected August opening is a forecast, not an actual completion of the first phase or campus.
Yates's undated DFW10 case study corroborates constituent identity; its described trade sequencing
and 2027 completion target do not become dated July 26 events.

DFW10 supplies the campus locator, not the selected project's entire physical scope. The operator's
facility and campus pages give 3330 Batchler Road; the county's exact Site address point matches
that address. Its landmark and parcel-ID fields are null, so the operator-address bridge is
essential and no literal county DataBank label is asserted. The point is not a building survey,
entrance, parcel or campus boundary, centroid, or observed active-work footprint.

The county layer and response identify stored EPSG:2276 NAD83 Texas North Central coordinates,
not the map-service extent's Web Mercator CRS. Independent PROJ conversion reproduces the
selected WGS84 point. The transformation operation's four-metre accuracy is not the point's
horizontal accuracy, which remains unknown. Independent comparison with all 175 full preceding
geometries, including polygon holes, found no intersection; full identity review found no
represented-campus alias. Building cards, later phases and the substation add no other site.

The county's copyright notice and blank map-item license field are retained separately from
DataBank's protected-content terms. No open licence or permission to reproduce the source works
is asserted. The draft distributes only minimal independently restated facts and the isolated
numeric address-point locator with attribution, not source prose, documents, maps, databases,
photographs, logos or raw captures. Public access is not treated as a redistribution grant.

The [Americas review](../sources/research-expansion-200-americas-round29-2026-09-09.json) records
the closed Red Oak route and four holds: anonymous Fort Worth district-level construction,
Snyder's incomplete capture and locator bridge, proposed Trumbull upgrades, and Culpeper's stale
underlying visit date. None adds to the accepted count. Bounded official successor checks found
no first-phase or whole-campus completion or cancellation before August 20; this is not an
exhaustive absence claim.

The [PA14 hold](../sources/research-expansion-200-europe-round29-2026-09-09.json) retains Icade's
June 10 powered-shell construction observation, the exact government PA14 address, and the
separately open-licensed BAN locator. Icade's explicit information-reuse restriction remains an
unresolved source-reuse gate in this checkpoint. The broad shell observation is not silently
assigned to an older Equinix phase key, and the full surrounding parcel is not a campus boundary.

The [MEEZA status review](../sources/research-expansion-200-root-round29-meeza-2026-09-09.json)
preserves fresh MV6 and MV8 construction reporting without substituting an office, QSTP locality
or MV2 address for an exact project locator. The independent
[identity supplement](../sources/research-expansion-200-asia-round29-meeza-identity-2026-09-09.json)
finds adjacency to MV2, not a verified same-plot statement; unresolved words in the issuer's
transcript are not strengthened using a third-party transcription. MV4's delivered expansion
and MV7's tender-stage design are excluded. [Asia's other holds](../sources/research-expansion-200-asia-round29-2026-09-09.json)
preserve the difference between investment or programme announcements and observed physical work.

No new roles, workloads, power metrics, certifications or independent imagery reviews are
inferred. Imagery remains 10/179, and blind review remains a fixed 20-row sample requiring
19 agreements from the expanded population. The 200-site objective and final-publication gates
remain incomplete.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-sixth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-sixth-reviewed --validate-only
```

## 2026-09-09: twenty-seventh reviewed checkpoint, 181 sites

The [twenty-seventh reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-twenty-seventh-reviewed/README.md)
adds five distinct campuses: Riot Rockdale, Google Elmina, dataR Rellingen, Microsoft
L'Ancienne-Lorette and Microsoft Lévis Charny. It contains 181 physical sites, 184 projects,
43 countries, 121 non-US sites and 795 evidence rows. The cumulative contract binds 559
source selections. Every preceding project, site, full geometry and evidence row is preserved.
This is 81 of the requested 100 additions; 19 remain. The 60 US sites leave room for at most
20 further US sites under the 40% country ceiling at 200.

The lifecycle cutoff remains August 20, with physical observations from May 22 onward.
Status, identity, geometry, source rights and imagery are reviewed independently:

- [Riot Rockdale](../sources/research-expansion-200-americas-round30-riot-2026-09-09.json):
  the August 10 issuer update explicitly puts the second AMD deployment under construction.
  The completed initial deployment stays unselected. A participant's public court filing,
  not a judicial finding, defines the exact facility address; the issuer independently bridges
  the same Rockdale campus identity. The native Texas address point is transformed from
  EPSG:3857, with unknown placement accuracy. No extra site is counted for later phases,
  mining buildings, acquired Rhodium assets or an unrelated lease announcement.
- [Google Elmina](../sources/research-expansion-200-asia-round30-2026-09-09.json):
  an original interview with Google's named infrastructure representative on August 15,
  published August 20, reports remaining construction. The office interview venue and
  unrelated Microsoft photograph are excluded. The preserved Wikidata campus key has a
  uniquely named CC0 point, zero coordinate references and unknown positional accuracy.
  No claim is made that the core and shell remain unfinished; a developer's later asset
  completion language is retained as an unselected scope caveat, with its rights unresolved.
- [dataR Rellingen](../sources/research-expansion-200-europe-round30-2026-09-09.json):
  the July 17 operator-hosted professional interview describes current implementation during
  construction separately from later operating preparations. Exact interview day is unknown.
  March's end-Q2 opening target is not an opening event. The municipality explicitly matches
  the data center to Kellerstraße 68; native OSM node 11707884695 supplies the exact mapped
  site-address point under ODbL. Its 2024 mapping date does not refresh physical status.
- [Microsoft Québec](../sources/research-expansion-200-americas-round30-microsoft-quebec-2026-09-09.json):
  the construction regulator's June 8 active-project register supplies two exact-address rows.
  Its aggregate four-center row is excluded. L'Ancienne-Lorette uses the unsuffixed 6505
  Yvon-Dolbec provincial record, transformed from EPSG:4617. Certified address validity is
  not location accuracy: the source explicitly labels the point interpolated. Lévis rejects
  the uncertain provincial locator and instead uses an interior point independently
  reconstructed from all 13 nodes of the named OSM campus polygon. That community shape
  is not an official boundary or work footprint, and the distinct QScale Q01 is not collapsed.

All five locators and the full Lévis source polygon were independently checked against all
176 preceding full geometries; the new sites were also checked against each other. There
were no intersections. No locality, headquarters or unrelated adjacent project was substituted.
Raw response hashes, byte counts, literal anchors, source enums and portable binding hashes
are checked. Raw articles, photographs and PDFs remain temporary and are not redistributed.

[DataVolt Tashkent](../sources/research-expansion-200-root-round30-datavolt-2026-09-09.json)
remains held: June financing is not fresh physical work, and the actual construction description
is from August 2025. Its consultant PDF also reserves third-party disclosure rights; no map
is digitized. [Piaseczno Energetyczna](../sources/research-expansion-200-root-round30-piaseczno-2026-09-09.json)
remains held because the municipality's preparatory-work wording concerns the separate
water-treatment station, not the data center. No Poland site is added.

No new roles, workloads, power metrics, certifications or imagery reviews are inferred.
Imagery remains 10/184; the fixed 20-row blind review requiring 19 agreements is incomplete.
The 200-site objective and final-publication gates remain incomplete.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-seventh-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-seventh-reviewed --validate-only
```

## 2026-09-09: twenty-eighth reviewed checkpoint, 183 sites

The [twenty-eighth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-twenty-eighth-reviewed/README.md)
adds CyrusOne Aurora and Firmus St Leonards/Launceston. It contains 183 physical sites,
186 projects, 43 countries, 122 non-US sites and 812 evidence rows. This is 83 of the requested
100 additions; 17 remain. Every prior row, source pin and full site feature is preserved.

CyrusOne's August 20 operator update reports permanent rooftop sound-wall and attenuation
installation at CHI2. This is a capital retrofit on the existing CHI1-CHI3 campus, not a new hall,
new IT capacity, routine generator testing or an assertion that the whole campus is unbuilt.
The state-named campus address is located by Census address-range interpolation with explicit
NAD83-to-WGS84 semantics. It does not locate the particular roof or imply surveyed accuracy.

Firmus's July 2 original ABC interview contains a directly attributed executive account of
contractors currently working on site. The broadcaster and speaker attribution remain explicit;
the transcript is not issuer-hosted and has not been acoustically verified. The September 2025
municipal agenda binds the new development to both 23 Killafaddy Road and 66-92 St Leonards Road.
The exact named existing LST01 building is a constituent-campus locator, not a new-hall footprint.
Bell Bay, Wesley Vale and the separate Melbourne project are not additional admissions here.
An unnamed operating Australian site in a September portfolio statement is retained as a caveat,
not treated as an observed completion of the new St Leonards factory before the cutoff.

The [root review](../sources/research-expansion-200-root-round31-review-2026-09-09.json)
records independent full-geometry checks against all 181 preceding sites, mutual comparison,
17 reverified source captures and the limits of each observation. Temporary captures disappeared
during an execution pause, so all selected source responses were freshly captured and rebound
before admission. Raw content remains in ignored local scratch storage, not the release.

Meta Aiken and DC BLOX North Augusta remain research holds: the June 3 original local article's
physical-work wording is reporter narrative alongside a named official's interview, without an
expressly attributed firsthand physical-status statement. Precise mapping or a legal parcel
match does not fill that evidence gap. Aiken's July 15 operational estimate is also not an
observed completion notice. The broader DPR community article is not a substitute lifecycle
source; its later failed refresh was stopped without an alternate-route retry.

No new roles, workload, capacity, jobs or imagery fields are inferred. Imagery remains 10/186;
the fixed 20-row blind review requiring 19 agreements remains incomplete. Expansion completion
and final-publication claims remain false.

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-eighth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-eighth-reviewed --validate-only
```

## 2026-09-09: twenty-ninth reviewed checkpoint, 184 sites

The [twenty-ninth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-twenty-ninth-reviewed/README.md)
adds one Prologis Trenton Project Mila campus. It contains 184 physical sites, 187 projects,
43 countries, 122 non-US sites and 823 evidence rows: 84 of the requested 100 additions,
with 16 remaining. All earlier checkpoints and the public v0.17 release stay unchanged.

The selected August 20 physical observation is the developer's own merit brief, filed through
its counsel and hosted by the Supreme Court of Ohio. It reports ongoing campus construction
and substantial progress on the exact consolidated property. The August 13 motion identifies
the developer as a Prologis affiliate. These are directly attributed company disclosures,
not court inspections, sworn construction affidavits or judicial findings about construction.
The later September 1 opinion orders certification of a proposed charter-amendment petition
for a special election; no project cancellation or construction ban is inferred from that writ.

The municipal certificate and preliminary plans connect Project Mila to its former parcels.
The county engineer returns the exact consolidated parcel R8000060000011 under the same
developer name; the older auditor layer independently matches all five predecessor parcels.
The 55-position county ring was transformed from NAD83 / Ohio South (US survey feet) to WGS84,
then used to derive a parcel-interior point. It is only a campus locator, not an approved
campus boundary, surveyed building position or new hall. The source polygon is not redistributed.
County mapping accuracy is unknown; the datum operation's reported four-metre accuracy is
not an estimate of locator accuracy. The whole parcel and point were checked against all
183 preceding full geometries, alongside identity and alias review.

Review and some source captures crossed UTC midnight into September 10 while the local work
date remained September 9. The contract records the later UTC review date; this does not move
the August 20 lifecycle cutoff. Raw-response bytes and hashes were verified before admission,
with extracted-text pointers clearly separated from PDF byte offsets. Municipal and county
rights limitations remain explicit, and only compact attributed facts and one point are included.

No new capacity, roles, workloads or imagery outcomes are selected. Imagery coverage remains
10/187, and the fixed 20-row blind-review requirement remains unresolved. Expansion completion
and final-publication flags are both false. Reproduce or validate with:

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-ninth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch twenty-ninth-reviewed --validate-only
```

## 2026-09-10: thirtieth reviewed checkpoint, 185 sites

The [thirtieth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-thirtieth-reviewed/README.md)
adds Google / Beale's Tulsa County Project Clydesdale campus. It contains 185 physical sites,
188 projects, 43 countries, 122 non-US sites and 829 evidence rows: 85 of the requested
100 additions, with 15 remaining. All preceding records and snapshots remain unchanged.

The selected August 19 joint developer announcement explicitly describes ongoing construction
at this named campus. Older groundbreaking, draft planning material and a forecast Q3 2027
completion do not refresh that observation. The existing Clydesdale campus key is preserved;
the selected project covers current campus construction without assuming a specific active
hall. Five planned lots, later phases and other Google campuses in Oklahoma are not extra sites.

A source-specific locator was derived from the public February 12 draft survey, using all
18 metes-and-bounds courses and the printed NAD83(2011) Oklahoma North section corners.
The traverse closes within 0.012 feet. Independent visual transcription and reconstruction
from the opposite corner reproduces the locator within 2.7 millimetres. These are numerical
consistency checks, not claims of positional accuracy. The point is inside the named draft
tract; it is not an approved plat, registered boundary, surveyed building or work footprint.
The survey's grid-to-ground factor is documented but not applied a second time to grid data.

The planning report's conflicting hearing year remains explicit. The official March 4, 2026
agenda establishes the meeting context, and draft minutes record withdrawal of the accelerated
permit request, not cancellation of the campus or approval of its plat. The independent
August 19 construction statement is later. All 184 preceding full geometries and campus
aliases were reviewed; neither the full reconstructed tract nor its point overlaps a selected site.

Six raw captures were rehashed independently, with the status anchor verified in the article
body rather than duplicate page metadata. Only attributed restated facts, derivation metadata
and one locator are distributed. Raw plans, complete course lists, reconstructed polygons,
publisher prose and imagery remain local research material; no open reuse licence is asserted.

No new metrics, roles, workloads or imagery outcomes are selected. Imagery remains 10/188;
the fixed 20-row blind-review requirement is unresolved. Both completion and final-publication
flags remain false. Reproduce or validate with:

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch thirtieth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch thirtieth-reviewed --validate-only
```

## 2026-09-10: thirty-first reviewed checkpoint, 186 sites

The [thirty-first reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-thirty-first-reviewed/README.md)
adds HIVE's Yguazú campus in Paraguay, limited to its current electrical-infrastructure expansion.
It contains 186 physical sites, 189 projects, 44 countries, 123 non-US sites and 841 evidence rows:
86 of the requested 100 additions, with 14 remaining. Every preceding row, geometry and snapshot
is preserved. The substation is a constituent of one data-center campus, not a separate utility site.

The issuer's August 14 MD&A describes ongoing construction of the Yguazú substation expansion
as of its information-through date. June 30 is the financial period end, not the construction
observation. June 22 distinguishes completed civil works from continuing substation construction
and a future Tier-III building scheduled to start in fall 2026. August 15 forecasts Q4 energization
and leaves the additional capacity's allocation undecided. Neither the completed original halls
nor the future building is selected as current construction. No new IT load, grid-capacity metric,
workload, role, operating-model or imagery observation is inferred.

The acquisition agreement identifies Zunz as owner of the acquired Yguazú data-center site.
The regulator's 2024 and 2026 declarations bind the combined data-center/substation project to
Finca 1534, Padrón 33. All six declaration pages were visually reviewed. The older design-stage
declaration and newer conditional environmental adjustment approval supply identity and scope,
not proof of current construction, comprehensive building authorization or legal compliance.
March 17, 2025 is retained as the agreement's effective date; its unverified SEC publication date
is explicitly null in the new root copy. The earlier unaccepted handoff remains unchanged.

The locator is the exact point returned by the public regulator GeoJSON response for project
83461, expedition 6240/2026. The public map's direct GeoJSON rendering and RFC7946 establish
the longitude/latitude WGS84 format contract; this is not an independent datum survey. The
slight difference in decimal serialization from the matching detail endpoint is retained without
averaging. It is a campus reference point, not a parcel boundary, building, entrance or work
footprint, and source-specific positional accuracy remains unknown. Full-geometry intersection
and identity/alias checks against all 185 preceding sites found no collision.

The [root review](../sources/research-expansion-200-root-round34-hive-yguazu-review-2026-09-10.json)
records twelve rehashed responses and separate verification of the two base64-decoded PDFs.
Independent read-only review confirmed all source bindings, six declaration pages, byte anchors,
full-geometry distinctness, inherited records and eleven byte-exact generated payloads.
Only compact restated facts, source attribution, hashes, coordinate-contract reasoning and one
locator are distributed. Raw filings, regulator declarations, maps and personal details remain
local research material; no open reuse licence is asserted.

Imagery coverage remains 10/189 and the fixed 20-row blind review requiring 19 agreements remains
incomplete. Expansion completion and final-publication claims are both false. Reproduce or validate:

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch thirty-first-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch thirty-first-reviewed --validate-only
```

## 2026-09-10: thirty-second reviewed checkpoint, 187 sites

The [thirty-second reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-thirty-second-reviewed/README.md)
adds one CapitaLand DC Chennai campus in Ambattur. It contains 187 physical sites, 190 projects,
44 countries, 124 non-US sites and 847 evidence rows: 87 of the requested 100 additions, with
13 remaining. All preceding rows, full geometries, source bindings and snapshots are preserved.

The July 29 issuer results explicitly report ongoing Chennai core-and-shell work in the latest
project-status table. The table incorporates July events, so July 29 is a publication-normalized
observation, not an inspection day or the June 30 financial period end. The adjacent Q4 completion
entry is a forecast. Independent bounded issuer and successor checks found no actual completion
or cancellation through August 20. A differing future schedule in a separate investor report is
retained as research context, not selected as a lifecycle event.

The operator property page binds Chennai 01 to Minerva Veritas and Pattravakkam Road. Its Taramani
office map pin remains rejected. The public environmental proposal supplies an active, versioned
Project Site KML and a matching Minerva site layout for Ambattur Ward B, Block 37, TS 19/2 and 20/2.
The public response includes both original and amended CAF records; both reference the same KML
UUID. The site-layout attachment carries the amendment number, which is not concealed as a frozen
2023 attachment. The exact public lookup method and document bindings are recorded in the
[research audit](../sources/research-expansion-200-asia-round36-chennai-geometry-2026-09-10.json).

The six-vertex source polygon is retained in WGS84 longitude/latitude under the normative KML
format contract. Conflicting CAF extent labels and its Linear shape label do not override the
actual KML polygon. The outline is a proponent-submitted project locator, not an officially
certified cadastral boundary, building footprint or current work extent. Its area differs from
the plan's superimposed area by approximately 0.9%; no fitting or silent correction is applied.
Source decimal tuples are preserved and real-world positional accuracy remains unknown. A
separate interior polygon centroid is derived solely for display. The combined data centre,
substation and ancillary yard count once, and full-geometry checks against all 186 preceding
sites found no overlap.

Six exact raw source captures were independently rehashed. Relevant complete PDF pages were
visually reviewed for status, site identity and the coordinate standard. Only compact factual
projections, attribution, hashes and the project outline are distributed; publisher PDFs,
HTML, KML, drawings, frontend code and personal details remain ignored local evidence.
No new capacity, roles, workload, operating model or imagery observation is inferred.

Imagery coverage remains 10/190; the fixed blind-review sample of 20 requiring 19 agreements is
unfinished. The inherited CGK host-estate locator remains a separately logged correction hold;
this addition does not certify that locator or alter the frozen baseline. Both expansion-complete
and final-publication flags remain false. Reproduce or validate:

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch thirty-second-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch thirty-second-reviewed --validate-only
```

## 2026-09-10: thirty-third reviewed checkpoint, 188 sites

The [thirty-third reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-thirty-third-reviewed/README.md)
adds the existing Digital Edge EDGE2 campus at Kuningan Mulia in Jakarta, where phase-3 electrical
and mechanical development remained unfinished on June 30. It contains 188 physical sites,
191 projects, 44 countries, 125 non-US sites and 854 evidence rows: 88 of the requested 100
additions, with 12 remaining. All preceding rows, full geometries and source bindings remain frozen.

The issuer's June financial statement explicitly describes the named phase as construction in
progress, separately from phase 2, which was completed and operating in 2025. The accounting
policy covers construction and machinery installation until completion. This supports broad
`under_construction`, not a particular installation milestone. The reported 99% is cost-based,
not measured physical progress. July 29 is authorization for issuance, not publication or a new
observation; publication day remains unknown. The forecast of completion during 2026, the 2024
whole-facility launch and current operational marketing do not settle phase-3 completion.
Bounded original-source successor checks found no authoritative completion or cancellation
through August 20; this is not exhaustive proof of absence.

The exact OSM way 1230327255 supplies a named EDGE2, EDGE DC, 15-storey data-centre building.
The operator announcement and historical specification sheet establish the street and facility
identity. PeeringDB facility 15081 provides explicitly selected third-party identity corroboration;
its geocode falls inside the OSM building, but its origin, datum and independence are unknown.
Neither the PeeringDB point nor the historical brochure's printed point is selected as geometry.
The brochure point differs by approximately 239 metres under a diagnostic WGS84 assumption.
That discrepancy remains unexplained, not disproved, and no averaging or forced match is applied.
The OSM website tag now redirects to a generic article, which is not current identity evidence.

The selected polygon copies the source node ring in order. OSM's separately captured coordinate
documentation supplies WGS84 semantics; source coordinates retain seven decimal places while
positional accuracy remains unknown. This community building outline is only a campus locator,
not an official boundary, surveyed footprint or current work extent. All 187 preceding full
geometries and aliases were screened with no overlap or match. EDGE1, CGK, DGE1 and DGE2 remain
separate; phase 3 adds one previously unrepresented campus, not an extra count for each phase.

The [root evidence audit](../sources/research-expansion-200-asia-round37-edge2-root-review-2026-09-10.json)
preserves the local-archive discovery, exact public object-API capture, rejected geocoder request,
stale website redirect and unresolved brochure discrepancy. Seven selected raw captures were
independently rehashed. Complete relevant PDF pages were visually reviewed. Only compact factual
projections and attributed OSM geometry are distributed, not raw documents, maps, HTML or media.
No new roles, capacity, workload, operating model or imagery observation is inferred.

Additional Haskell, ARNES Maribor and Equinix FR15 findings remain research-only: energy-zone
geometry does not locate Google's campus, and exact location evidence does not supply missing
in-window physical status. The inherited CGK host-estate locator remains a separately logged
correction hold, not certified by EDGE2's admission. Imagery coverage is still 10/191; the fixed
20-row blind review requiring 19 agreements is unfinished. Expansion-complete and final-publication
flags remain false. Reproduce or validate:

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch thirty-third-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch thirty-third-reviewed --validate-only
```

## 2026-09-10: thirty-fourth reviewed checkpoint, 189 sites

The [thirty-fourth reviewed draft](../verified_construction_core/2026-08-20-v0.18-draft-thirty-fourth-reviewed/README.md)
adds STACK's Bossier Highway 3 Technology Park campus in Louisiana. It contains 189 physical
sites, 192 projects, 44 countries, 125 non-US sites and 860 evidence rows: 89 of the requested
100 additions, with 11 remaining. Every preceding row, feature and source binding is preserved.

STACK's June 10 release explicitly says construction is underway at both its Caddo and Bossier
campuses. Only the independently identified Bossier member is selected. The publication date
normalizes its contemporary broad construction statement; it is not an independently dated
inspection or start day. The parish's March 18 proceedings, published April 15, and March 20
official report bind STACK and Amazon to Highway 3 Technology Park. The six-building development
on lots 3 and 4 with supporting infrastructure is one campus, not six sites. Amazon's explicitly
August 18-updated disclosure is successor context only. Bounded original-source checks found
no actual Bossier completion or cancellation through August 20, not exhaustive proof of absence.
Caddo and the third planned Shreveport campus are not merged or counted here.

The locator comes from the smaller black dashed Project Site vector in the applicant's map
published with Corps notice MVK-2025-00855. It is not the larger red landholding's centroid or
the separate narrative point with unstated datum. The exact embedded WKT matches NAD83(2011)
/ Louisiana North in US survey feet. Adobe's original ExtensionLevel 3 specification explicitly
places the geographic registration controls in the datum underlying that WKT. Four five-decimal
controls map the 335-point PDF vector into source projected coordinates by disclosed bilinear
interpolation; they are not silently assumed to be WGS84.

Independent reproduction yields the interior point `[-93.73567, 32.75561]` in longitude/latitude.
The source's tiny self-touch is explicitly normalized with `make_valid`; the original points,
one tiny resulting hole and unchanged representative point are recorded. The datum operation's
two-metre accuracy is not positional accuracy of the drawing. Source positional accuracy remains
unknown. The Corps says applicant information was not otherwise verified for regulatory
compliance; this is a government-published proponent locator, not an official campus boundary,
survey, building footprint or observed work extent. The conflicting Section 2/32 northern map
label and differing mapped/plat/lease areas remain disclosed rather than fitted or corrected.
The larger full landholding and all 188 preceding geometries and aliases were screened with no
intersection or match.

The [root evidence audit](../sources/research-expansion-200-americas-round38-stack-bossier-root-review-2026-09-10.json)
records the independent derivation, exact source hashes, complete relevant PDF-page review and
rejected Adobe redirect/wrong-version capture. Six selected source bodies and the parish terms
were rehashed. Only compact attributed facts and numerical derivation inputs are distributed;
raw documents, maps, HTML, media and personal details stay ignored. Parish website rights are
not extended to the newspaper, proponent map or Adobe specification. No new roles, capacity,
workload, operating model or imagery observation is selected.

The [round38 Asia research packet](../sources/research-expansion-200-asia-round38-2026-09-10.json)
adds no admissions: SEL02's exact Ansan parcel is identified but lacks georeferenced geometry;
Baoji's approved plan has an unresolved coordinate frame; True IDC's seventh Northern Bangkok
facility must not be conflated with East Bangna phases. The inherited CGK host-estate locator
still requires a versioned correction before a verified 200-site completion claim. Imagery is
still 10/192, and the fixed 20-row blind review requiring 19 agreements remains unfinished.
Expansion-complete and final-publication flags remain false. Reproduce or validate:

```sh
.venv/bin/python scripts/build_expansion_200_draft.py --batch thirty-fourth-reviewed --output-dir /absolute/new/draft-directory
.venv/bin/python scripts/build_expansion_200_draft.py --batch thirty-fourth-reviewed --validate-only
```

## 2026-09-10: round39 locator and successor review

The selected checkpoint remains 189 sites and 192 projects. These research findings add no
campuses and do not change any frozen input, admission contract or release artifact.

- [Caddo State Line](../sources/research-expansion-200-americas-round39-caddo-2026-09-10.json):
  STACK's June 10 physical-status statement qualifies, but the public Blanchard water authorization
  does not name its customer or include a site exhibit. Caddo's August 17 minutes remand the two
  resolutions to committee, rather than enact a moratorium. The exact applicant-to-parcel bridge
  and source-CRS locator remain missing. Bossier and the third Shreveport proposal stay separate.
- [DCI/Koramco SEL02](../sources/research-expansion-200-asia-round39-sel02-2026-09-10.json):
  an additional official plan table corroborates Seonggok-dong parcel 712, but supplies no map.
  Two directory pins disagree by about 3.15 km and neither is parcel-bound; neither is selected.
  The issuer's June 9 media-listing date is not the ceremony date. Conflicting third-party
  ceremony dates are retained separately, and no exact primary event day is invented.
- [CGK correction](../sources/research-expansion-200-cgk-locator-round39-2026-09-10.json):
  a public landowner financial filing names Digital Gayana Ekagrata as a customer, without
  identifying its parcel. The estate-wide masterplan and corporate-domicile table likewise do
  not resolve the campus. The inherited host-estate polygon still needs a versioned correction
  before a verified 200-site completion claim; CGK's correction cannot add a new site.

All 35 referenced raw capture hashes and byte counts were independently rechecked locally;
the current 189-site draft validator still passes. Complete relevant PDF pages were visually
reviewed, and the CGK packet received a separate peer review. Only concise attributed findings
and custody metadata are retained in Git. Raw documents, maps, HTML, rendered pages and personal
details remain ignored. No restricted-presentation content, denied-service bypass, or fabricated
geometry is included. Eleven further distinct campuses and the CGK correction remain required.
