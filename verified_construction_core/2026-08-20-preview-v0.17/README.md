# Verified Construction Core v0.17 preview

This tracked, non-final preview contains **100 physical sites**
and **103 linked projects** in 40
countries. The v0.17 delta adds exactly 20 distinct physical sites to the byte-frozen v0.16
artifact. Every new project has a dated authoritative physical-status observation effective no
later than the fixed 2026-08-20 lifecycle cutoff and a separately reviewed locator.

The count and diversity milestones are now met: 100 physical sites and 40 countries. This remains
a preview because imagery-review coverage and the required blind review are incomplete. Those
unmet gates remain explicit in `selection-report.json`, so `publishable_as_final` is false.

All v0.17 geometries are locators, not official boundaries or construction footprints. Source
precision and rights constraints are preserved per row. Raw HTML, PDFs, API responses, map tiles,
imagery, and publisher media are not redistributed. Capacity, energy, efficiency, roles,
workloads, customers, tenants, users, and operating model remain unselected and unknown for all
20 new projects.

## Files

- `projects.csv`: one row per selected physical construction project
- `sites.csv`: one row per distinct physical site
- `sites.geojson`: reviewed locator or boundary geometry for each physical site
- `evidence.csv`: locally bound evidence and exact usage roles
- `selection-report.json`: cohort, provenance, rejection, and release-gate audit
- `schema.json`: field and v0.17 scope semantics
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
advice. Unknowns remain unknown, and no capacity, role, workload, energy, efficiency, or lifecycle
claim is inferred from geometry.
