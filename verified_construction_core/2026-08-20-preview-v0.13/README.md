# Verified Construction Core v0.13 preview

This tracked, non-final preview contains **59 physical sites**
and **62 linked projects** in 27
countries. Every project retains a dated authoritative physical-status observation and a reviewed
geometry scope. Five project rows carry official boundaries; the remaining 57 are explicit project
or campus locators, never construction footprints by implication.

The six-row v0.13 delta adds Goodman SYD01, firstcolo FRA7, XTX Kajaani DC2, QTS Cambois
earthworks, Bitzero Namsskogan power-infrastructure foundations, and Ezditek RUH01 Phase 1. It
uses three source points and three source polygons. The XTX and Bitzero cadastral polygons are
official-source parent-campus locators, not official publication boundaries; the RUH01 building
polygon is community mapped and remains non-official. QTS uses only the wider-campus approximate
NGR point, never the separate Phase A point. All v0.13 lifecycle dates are no more than 90 days old
at the fixed **2026-08-20** cohort cutoff.

The tracked capture retains compact facts, derived geometry, exact raw-source byte counts and
hashes, and source-specific rights. It does not redistribute the all-rights PDFs or SEC HTML, and it
does not retain or interpret Esri imagery. The volatile NLS WFS raw-response hash identifies the
reviewed response only; it is not a promise that a later live response will be byte-identical.

The National Land Survey of Finland parcel geometry is redistributed under CC BY 4.0 with NLS
attribution. The Kartverket parcel geometry is redistributed under CC BY 4.0 with © Kartverket.
The RUH01 geometry is derived from OpenStreetMap and is made available under ODbL 1.0 with
© OpenStreetMap contributors. Applicant, issuer, and company sources remain fact-extraction-only.

Final-release gates remain explicit in `selection-report.json`. The final artifact still requires at
least 100 physical sites, 40 countries, 50 non-U.S. sites, complete imagery-review outcomes, a
20-site blind review, and a clean-clone rebuild. Until every gate passes,
`publishable_as_final` is false.

## Files

- `projects.csv`: one row per selected physical construction project
- `sites.csv`: one row per distinct physical site
- `sites.geojson`: reviewed locator or boundary geometry for each physical site
- `evidence.csv`: locally bound evidence and exact usage roles
- `selection-report.json`: cohort, provenance, rejection, and release-gate audit
- `schema.json`: field and v0.13 scope semantics
- `map.html`: deterministic offline map; no tile requests
- `manifest.json` and `manifest.sha256`: byte inventory and trust root
- `ATTRIBUTION.txt`: source-specific attribution and terms

## Legal notice

City of Chicago data notice

Attribution: City of Chicago
Terms: https://www.chicago.gov/city/en/narr/foia/data_disclaimer.html

Required disclaimer:
“This site provides applications using data that has been modified for use from its original source, www.cityofchicago.org, the official website of the City of Chicago. The City of Chicago makes no claims as to the content, accuracy, timeliness, or completeness of any of the data provided at this site. The data provided at this site is subject to change at any time. It is understood that the data provided at this site is being used at one’s own risk.”

Additional terms reminder:
Comply with any additional Terms of Use set forth by the City agency or department providing data used by the software application, or other secondary or derivative application, including, without limitation, requirements to include additional citations or disclaimers at the site where the application can be accessed or downloaded.

This preview is an evidence product, not legal, surveying, investment, engineering, or operational
advice. Unknowns remain unknown, locators are not silently promoted to footprints, and no capacity,
role, workload, energy, efficiency, or lifecycle claim is inferred from geometry. The preview is
not final while `publishable_as_final` is false.
