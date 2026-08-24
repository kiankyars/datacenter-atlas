# Verified Construction Core v0.15 preview

This tracked, non-final preview contains **73 physical sites**
and **76 linked projects** in 27
countries. Every project retains a dated authoritative physical-status observation and a reviewed
geometry scope. Five project rows carry official boundaries; the remaining 71 are explicit project
or campus locators, never construction footprints by implication.

The five-row v0.15 delta adds eStruxture CAL-3 in Canada, atNorth FIN04 and Hyperco Loviisa in
Finland, CDC Beard BE1 in Australia, and Green Mountain FRA-Mainz in Germany. CAL-3 uses the exact
point published in its first-party datasheet. FIN04 uses the exact three-component
National Land Survey of Finland (NLS) property
MultiPolygon under CC BY 4.0 only as a shared-campus locator after a Kouvola permit binds atNorth,
Lossitie 26, and property 286-423-20-1. Hyperco uses a CC BY 4.0 Ryhti permit-building point
cross-identified to the Loviisa permit. FRA-Mainz uses the official Energieatlas project point as a
compact factual locator.

The ACT development-application plan identifies CDC's BE1 Data Centre at Block 24 Section 11 Beard.
The corresponding CC BY 4.0 ACT block polygon is published exactly, but its source lifecycle is
`RETIRED`; it is explicitly a historical project locator only, never a current parcel, present legal
boundary, campus boundary, project footprint, building footprint, or current-work extent. Every
v0.15 row has `official_boundary=false` and unknown numeric horizontal accuracy. Raw PDFs, HTML,
all-rights-reserved responses, and imagery are excluded.

Final-release gates remain explicit in `selection-report.json`. The final artifact still requires at
least 100 physical sites, 40 countries, complete imagery-review outcomes, a 20-site blind review,
and a clean-clone rebuild. The 50 non-U.S.-site minimum is now met. Until every gate passes,
`publishable_as_final` is false.

## Files

- `projects.csv`: one row per selected physical construction project
- `sites.csv`: one row per distinct physical site
- `sites.geojson`: reviewed locator or boundary geometry for each physical site
- `evidence.csv`: locally bound evidence and exact usage roles
- `selection-report.json`: cohort, provenance, rejection, and release-gate audit
- `schema.json`: field and v0.15 scope semantics
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
