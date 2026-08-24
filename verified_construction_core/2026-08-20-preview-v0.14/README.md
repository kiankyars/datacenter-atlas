# Verified Construction Core v0.14 preview

This tracked, non-final preview contains **68 physical sites**
and **71 linked projects** in 27
countries. Every project retains a dated authoritative physical-status observation and a reviewed
geometry scope. Five project rows carry official boundaries; the remaining 66 are explicit project
or campus locators, never construction footprints by implication.

The nine-row v0.14 delta adds Microsoft Alviso, Bitdeer Wenatchee, Sabey Austin, Microsoft Heath,
Microsoft New Albany, Bitdeer Massillon, Microsoft Hebron, QTS Cedar Rapids, and Jefferson Lab
JLDC. Seven sites use United States Census Bureau Public_AR_Current address matches only as
parent-campus locators. QTS
uses its first-party CDR1 DC1 page pin only as a shared-campus locator, while the Census Fairfax
normalization remains corroboration. Alviso uses the City of San Jose address point cross-identified
to Microsoft and CP23-016 as a project locator. Every point has `official_boundary=false` and unknown
numeric horizontal accuracy.

QTS publishes the selected street address with a Cedar Rapids label, while Census returns Fairfax for
the same address and ZIP. Jefferson Lab publishes ZIP 23606, while Census returns 23605; its point is
only a broad laboratory-campus locator, not the JLDC building. The Washington and Licking County
parcel polygons, the City Major Private Development polygon, all source HTML/PDF, and all imagery are
excluded. Only compact facts and exact raw-response byte/hash pins are retained.

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
- `schema.json`: field and v0.14 scope semantics
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
