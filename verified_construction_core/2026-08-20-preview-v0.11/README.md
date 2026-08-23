# Verified Construction Core v0.11 preview

This tracked, non-final preview contains **48 physical sites**
and **51 linked projects** in 26
countries. Every project retains a dated authoritative physical-status observation and an exact
reviewed geometry scope. Five project rows carry official boundaries; the remaining 46 are
explicit project or campus locators, never construction footprints by implication.

The one-row v0.11 delta adds the IIJ Shiroi DCC Phase 3 Server Building. IIJ evidence remains the
sole lifecycle and planned-capacity authority: under construction as of 2026-06-25 and exactly one
planned 10 MW grid_connection_mw observation. The optional 25 MW expandability ceiling is not
published as installed, contracted, current, or additive capacity. No operating model, workload,
owner, operator, user, tenant, or customer is inferred; the source developer string is explicitly
excluded because developer is outside the public role schema.

Chiba Prefecture binds the exact campus name 白井データセンターキャンパス to
白井市桜台５－１－１. The 桜台５ address prefix corresponds textually to the e-Stat feature name
桜台五丁目; no address point or point-in-polygon containment is asserted. The full official 2020
census small-area Polygon is published only as a broad named-area campus locator. It is not a
campus, parcel, building, Phase 3, construction, security, cadastral, or administrative boundary.
The CSV latitude/longitude pair is e-Stat's source-published statistical-boundary shape center and
only a display anchor for that full Polygon; it must never be used standalone as site or project
geometry. The reported 55,117.019 square metres is only the statistical feature's area, never IIJ
site area.

Portal Site of Official Statistics of Japan (e-Stat); Statistics Bureau of Japan; selected Shapefile feature converted to GeoJSON by Data Center Atlas.

The fixed cohort lifecycle/status cutoff is 2026-08-20. The e-Stat and Chiba evidence was captured,
and its geometry/identity use accepted, on 2026-08-23; it does not update cohort lifecycle state.
For preview compatibility, `reviewed_at` remains an alias for the lifecycle cutoff; the manifest and
selection report separately expose `geometry_identity_reviewed_at`.

The artifact is deterministic and rebuildable in a clean clone from the 74 manifest-bound portable
inputs plus the byte-frozen v0.10 artifact. Ignored v97 and v14 payloads are optional complete
hydrated cross-checks, not build dependencies. The v0.11 row inherits the not-reviewed imagery
outcome and remains independent_imagery_verification=false.

## City of Chicago terms inherited from v0.10

City of Chicago data notice

Attribution: City of Chicago
Terms: https://www.chicago.gov/city/en/narr/foia/data_disclaimer.html

Required disclaimer:
“This site provides applications using data that has been modified for use from its original source, www.cityofchicago.org, the official website of the City of Chicago. The City of Chicago makes no claims as to the content, accuracy, timeliness, or completeness of any of the data provided at this site. The data provided at this site is subject to change at any time. It is understood that the data provided at this site is being used at one’s own risk.”

Additional terms reminder:
Comply with any additional Terms of Use set forth by the City agency or department providing data used by the software application, or other secondary or derivative application, including, without limitation, requirements to include additional citations or disclaimers at the site where the application can be accessed or downloaded.

This is not the final 100-site Verified Construction Core v1. Its final-release gates remain
unsatisfied and publishable_as_final is false.
