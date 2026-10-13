# Country research

Work in this order: **United States → China → United Kingdom → Germany → Japan**. Give each
contributor a bounded country pass using local primary sources. Each pass finds missing sites,
checks later reports for existing sites and resolves known corrections. Share the same record
format and check names and campus aliases across assignments before adding a site.

The [IEA](https://www.iea.org/reports/energy-and-ai/energy-supply-for-ai) identifies the US and
China as the largest markets. [Synergy's August 2026 research](https://www.srgresearch.com/articles/us-rises-again-as-synergy-updates-its-ranking-of-hyperscale-data-center-locations)
also places most large hyperscale locations in these two countries. [CBRE's UK outlook](https://www.cbre.com/insights/books/uk-real-estate-market-outlook-2026/data-centres)
identifies the UK as Europe's largest commercial data-centre market. Operator filings and
government records support individual records; market reports provide background.

Before this pass, the Atlas held 66 US, one mainland China, five UK, 17 German and two Japanese
sites. These are Atlas coverage counts, not national totals. China and Japan need considerably
more local-language research.

## Coverage and updates

Catalogue announced, permitted, under-construction, completed and operating projects distinctly. An
announcement needs a dated primary source naming the project. Permitted status needs issued
consent for the data-centre development itself, with authority, date and approved work recorded;
utility, microgrid or air permits alone are insufficient. Physical work, completion and operation
each need supporting evidence. An opening target or elapsed time cannot establish any of them.

Keep sites when they complete, open, pause, close or change status. Update the existing record
and retain its earlier evidence. New admissions need a sourced site location and status evidence
from the 90 days before the data update. Review later reports and keep the date the evidence
actually supports; a new research pass does not make an old observation current. Publish supported
additions and updates as they are ready.

Retention does not reverse corrections to unsupported claims. The removed Scala records stay
removed unless new primary evidence supports their identity, location and status. A withdrawal
does not assert completion or cancellation.

## 13 October 2026

- Added Edinburgh's Advanced Computing Facility CR4 extension: steel-frame observation dated
  22 September and a named campus-building map feature matched to the university's address.
- Updated Oracle Project Jupiter from a 27 May observation to the operator's 14 September
  report of building construction. The adjacent microgrid permitting case is a different scope.
- Corrected the inherited Scala source-date issues and three locations whose geometry represents
  surrounding industrial estates. Full change lists and source projections accompany the data.
- After consolidating the 231 source records, added NorthC FRA01 using its 18 September
  preparatory-work statement and the exact Frankfurt municipal building-address point for
  Mainzer Landstraße 695. The point locates the address; it is not a construction boundary.
- Refreshed the existing Frontier record from Oracle's construction media dated 8 September
  and the existing Saline Barn record from Oracle's 28 September current-work statement.
  Frontier retains its explicitly labelled county locator; neither refresh adds another site.

## Candidate queue

- **United States:** Microsoft Silver Springs now has the service-provided centroid and outline
  of Microsoft-owned county parcel 015-141-14, but its September work report has only month
  precision. Silver Springs and Microsoft Lyle Creek therefore remain queued without invented
  observation days. Frontier's status has been refreshed; its exact campus locator remains
  unresolved, so the imported county-centre point retains its administrative precision.
- **China:** the [GDS second-quarter results](https://investors.gds-services.com/index.php/news-releases/news-release-details/gds-holdings-limited-reports-second-quarter-2026-results)
  are an operator lead; aggregate construction area does not identify individual sites. Review
  the [China Mobile Beijing No.6 parcel procurement](https://ggzyfw.beijing.gov.cn/jyxxzbhxrgs/20260901/5692101.html)
  for a named proposal and location. The procurement does not itself establish development consent
  or physical work. Start with Beijing, Shanghai and Guangdong operator portfolios and local records.
  The follow-up reviewed VNET, GDS, China Mobile and regional government reports; no additional
  scope met the location and recent-evidence gates. VNET's August results report June observations.
- **United Kingdom:** keep Edinburgh's CR4 extension on the existing ACF campus as its status
  changes. Kao Manchester has evidence of site preparation and electrical enabling works; confirm
  its precise site location and obtain a later primary observation than 1 July, now 104 days old.
  The operator expects building construction in 2027 and operations in 2028; those are forecasts.
- **Germany:** NorthC FRA01 is admitted. VIRTUS Wustermark still needs the electrical works tied
  to the correct campus and phase. The UVP record identifies Wustermark1 module5 backup power,
  not the whole development; its administrative bounding box is not a precise locator.
  The current operator pages conflict on 204 versus 300 MW IT and retain inconsistent one-campus
  versus two-location descriptions, so source-specific claims remain separate.
- **Japan:** Zeus OSA1's December 2025 start predates the new-admission window. Look for later
  primary evidence of its actual status and exact campus location, including any completion or
  opening. Keep IIJ Shiroi and Tomakomai updates separate from new campuses.
  The follow-up also checked CyrusOne OSK1 and DayOne Kodaira. A lease or ceremony does not
  establish physical work; later evidence and exact phase identity remain necessary.

The country packets under `sources/research-countries-2026-10-13-*` retain checked candidates,
sources and the missing fact for each hold. The Scala audit is in
`sources/research-scala-status-2026-10-13.json`. A held candidate does not count as a site.
The exact-day successor is defined in `definitions/atlas-research-2026-10-13.json` and published
as `verified_construction_core/2026-10-13-research`: 414 projects across 390 sites. Its three
actions preserve the complete consolidated source snapshot and identity mapping. Oracle's
Frontier caption date is stored as an explicit observation date; the undated containing page
retains an unknown publication date.
