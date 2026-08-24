# Verified Construction Core v0.16 preview

This tracked, non-final preview contains **80 physical sites**
and **83 linked projects** in 33
countries. Every project retains a dated authoritative physical-status observation and a reviewed
geometry scope. Five project rows carry official boundaries; the remaining 78 are explicit project
or campus locators, never construction footprints by implication.

The seven-row v0.16 delta adds Scala SBOGZB01 in Colombia, Telecom Egypt RDH2, Racks Central RCJM1
in Malaysia, Telia's new Vilnius data center in Lithuania, Pure DC AMS01 in the Netherlands, Start
Campus SIN02 in Portugal, and Digital Edge CGK1 in Indonesia. All seven are distinct physical sites.
Mexico SMEXTP01 is excluded because its current authoritative status is operational and therefore
outside the physical-status cohort.

The source-selection ledger is deliberately split: 81 selected projects and 450 nonselected rows
come from the frozen 531-row v97 construction pipeline after the v0.16 reviewed allowlist and two
hash-pinned successor-status overlays. Pure DC AMS01 and Start Campus SIN02 are two explicitly
post-v97 portable projects. They bring the artifact cohort to 83 projects but are not represented as
v97 rows. `selection-report.json` records both populations and the exact first-failure derivation.

SBOGZB01 uses an exact CC BY 4.0 IDECA official address point only as a Zona Franca Bogotá campus
locator. AMS01 uses an exact PDOK BAG Tower 1 address point only as a broad campus locator. SIN02
uses an approximate 25-metre centroid derived from the official APA GeoPDF for the shared
multi-phase SIN02-06 area; it is not a SIN02 work point or footprint. RDH2, RCJM1, Telia Vilnius,
and CGK1 use ODbL OpenStreetMap geometry only as broad campus locators: respectively the named
Smart Village host development, the reproducible union of Iskandar Halal Park Phases 1 and 2, the
named Telia construction area, and the entire Greenland International Industrial Center host estate.
No community geometry is an official boundary, and no OSM tag supplies physical-status evidence.

Raw HTML, PDFs, GeoPDFs, drawing bundles, API responses, imagery, and all-rights-reserved source
artifacts are excluded. Capacity, energy, efficiency, roles, workloads, customers, tenants, users,
and operating model remain unselected and unknown for every new row.

Final-release gates remain explicit in `selection-report.json`. The final artifact still requires at
least 100 physical sites, 40 countries, complete imagery-review outcomes, a 20-site blind review,
and a clean-clone rebuild. The non-U.S.-site minimum is met. Until every gate passes,
`publishable_as_final` is false.

## Files

- `projects.csv`: one row per selected physical construction project
- `sites.csv`: one row per distinct physical site
- `sites.geojson`: reviewed locator or boundary geometry for each physical site
- `evidence.csv`: locally bound evidence and exact usage roles
- `selection-report.json`: cohort, provenance, rejection, and release-gate audit
- `schema.json`: field and v0.16 scope semantics
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
