# Country research

Prioritize the largest markets, with extra attention to missing coverage. The initial country
passes are the United States, China, the United Kingdom, Germany and Japan. This is a research
order, not a claim that those countries have the same ranking under every capacity measure.

The [IEA](https://www.iea.org/reports/energy-and-ai/energy-supply-for-ai) identifies the US and
China as the largest markets. [Synergy's August 2026 research](https://www.srgresearch.com/articles/us-rises-again-as-synergy-updates-its-ranking-of-hyperscale-data-center-locations)
also places most large hyperscale locations in these two countries. [CBRE's UK outlook](https://www.cbre.com/insights/books/uk-real-estate-market-outlook-2026/data-centres)
identifies the UK as Europe's largest commercial data-centre market. Operator filings and
government records are the sources for individual admissions; market reports set research priority.

Before this pass, the Atlas held 66 US, one mainland China, five UK, 17 German and two Japanese
sites. These are Atlas coverage counts, not national totals. China and Japan need considerably
more local-language research.

## 13 October 2026

- Added Edinburgh's Advanced Computing Facility CR4 extension: steel-frame observation dated
  22 September and a named campus-building map feature matched to the university's address.
- Updated Oracle Project Jupiter from a 27 May observation to the operator's 14 September
  report of building construction. The adjacent microgrid permitting case is a different scope.
- Corrected the inherited Scala source-date issues and three locations whose geometry represents
  surrounding industrial estates. Full change lists and source projections accompany the data.

The next site admissions to resolve are Microsoft Silver Springs and Vantage Frontier in the
US, and NorthC FRA01 in Germany. All have physical-work evidence, but their precise geographic
binding remains incomplete. Exact addresses alone are not numeric locations; street and town
centres were rejected. Microsoft Lyle Creek's September work update has only month precision,
so it has not been converted into an invented observation day.

China follow-up: the [GDS second-quarter results](https://investors.gds-services.com/index.php/news-releases/news-release-details/gds-holdings-limited-reports-second-quarter-2026-results)
are an operator lead, but aggregate area under construction cannot create individual sites.
The [China Mobile Beijing No.6 parcel procurement](https://ggzyfw.beijing.gov.cn/jyxxzbhxrgs/20260901/5692101.html)
identifies a project location but does not establish physical work. Start with Beijing,
Shanghai and Guangdong operator portfolios and match named projects to local construction reports.

Japan follow-up: Zeus OSA1's December 2025 start is older than this pass's new-site observation
window; find a recent physical-work report and exact campus location. Keep IIJ Shiroi and
Tomakomai updates separate from new campuses.

The country packets under `sources/research-countries-2026-10-13-*` retain checked candidates,
sources and the missing fact for each hold. The Scala audit is in
`sources/research-scala-status-2026-10-13.json`. A held candidate does not count as a site.
