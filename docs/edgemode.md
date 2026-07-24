# EdgeMode and SEC EDGAR

EdgeMode is useful as a first-party operator/developer lead source, but it is not a global
data-centre database. The only publication-eligible lane in the current assessment is a bounded,
review-only pilot derived from EdgeMode's public SEC filings.

The immutable assessment is
`source_assessments/edgemode-2026-07-18-v1/`. Its manifest SHA-256 is
`f8b53877a54a831130d0099b4c37ea479b904e91a89963131206e1e3b35316e7`.

## Access and rights boundary

EdgeMode's official site is human-facing. Its sitemap lists three pages and no documented
facility-data API. The site footer says “All rights reserved,” and no affirmative license for
automated retrieval, storage, redistribution, derivatives, or commercial reuse was found. The
direct `edgemode.io` lane therefore fails closed: no bulk fetch, cache, or direct release.

SEC EDGAR is a separate rights root. The SEC says public EDGAR filing content is
[free to access and reuse](https://www.sec.gov/about/webmaster-frequently-asked-questions),
allows scripted access subject to its fair-access rules, and exposes an unauthenticated
[company submissions API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
The API is operated by the SEC, not EdgeMode. The pilot consequently uses the source family
`sec_edgar_edgemode`; it does not imply permission to scrape EdgeMode's site.

This is a conservative source-governance decision, not legal advice. The cited SEC reuse
statement is unqualified but does not separately use the word “commercial.” The assessment treats
that unqualified reuse permission as sufficient for this small derived pilot while retaining no
raw pages.

## Coverage and reliability

The bounded pilot contains nine review rows:

- eight named project identities disclosed across Spain and Panama; and
- one additional `Palma` land-site label whose relationship to those eight identities is
  unresolved.

The unique facility count is deliberately `null`. EdgeMode's website describes five Spain
campuses totaling at least 1.5 GW of IT load, while its SEC filings describe eight projects,
increase the Spain-based aggregate to 4,350 MW, and separately describe a 1,000 MW Panama
project. Those scopes are not reconciled.

The January 2026 8-K described
[3,550 MW across eight projects](https://www.sec.gov/Archives/edgar/data/1652958/000168316826000590/edgemode_8k.htm).
The March amendment then increased the
[Spain-based aggregate to 4,350 MW](https://www.sec.gov/Archives/edgar/data/1652958/000168316826002146/edgemode_8k.htm).
The Q1 10-Q describes five original SPV names containing 300 MW, a later management plan of
360 MW per original site, Villasequilla at 600 MW, Tomelloso at 450 MW, and Tocumen at 1,000 MW.
The resulting named Spain project-scoped sum is 2,850 MW, leaving 1,500 MW unallocated against
the later aggregate. The pilot therefore emits source-scoped statements but no typed or current
facility capacity.

The filings also make the development risk explicit: permits, fibre, financing, agreements, and
eventual operation were not assured as of the Q1 filing. A June filing calls the Malpica/Mora
project “in-development” in connection with a non-binding sale offer, and a July filing describes
leasehold land in Cordoba, Palma, Vianos, and Caceres under another non-binding term sheet. These
are developer disclosures, not physical-construction verification.

## Field utility

The lane can support:

- developer project/SPV and locality labels;
- intended AI, HPC, colocation, cloud, and Tier 3 descriptors;
- source-scoped planned/in-development/ready-to-build language; and
- source-scoped MW statements with explicit reconciliation caveats.

It does not provide structured coordinates, verified construction lifecycle, commissioning dates,
current site-allocated or consistently typed MW, annual energy use, metered consumption, PUE, or
verified operational workload. All nine rows have null Atlas lifecycle, coordinates, gross MW, IT
MW, annual energy, and PUE. There are zero construction-verified and zero typed-capacity rows.

## Fail-closed use

The pilot may enter candidate review only. It must not:

- auto-merge with an existing facility;
- promote developer language to proposed or under-construction lifecycle without separate
  physical or permitting evidence;
- infer coordinates from locality labels without a separately licensed geocoder and analyst
  review;
- treat intended AI/HPC use as an operating workload; or
- type or total MW until the metric scope and current site allocation are independently resolved.

The validator performs no network requests:

```sh
python3 scripts/validate_edgemode_assessment.py
```

The most recent filing in the probed SEC submissions metadata was dated 2026-07-15. The latest
data-centre-relevant filing reviewed for the pilot was dated 2026-07-06, so future refreshes must
start from the pinned CIK cutoff rather than recrawling the whole archive.
