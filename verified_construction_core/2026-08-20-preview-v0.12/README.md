# Verified Construction Core v0.12 preview

This tracked, non-final preview contains **53 physical sites**
and **56 linked projects** in 26
countries. Every project retains a dated authoritative physical-status observation and a reviewed
geometry scope. Five project rows carry official boundaries; the remaining 51 are explicit project
or campus locators, never construction footprints by implication.

The five-row v0.12 delta adds CoreWeave Lancaster Phase 1, Lancium Abilene's remaining six-building
expansion, NTT TX4, QTS York Building 1, and TRG HOU2. Each project is bound by an explicit
project_targets relationship to a distinct parent campus and by hash-pinned curated source evidence.
Only physical status, campus-address identity, and the shared geometry evidence are selected. No
source metric, role, workload, operating model, owner, operator, user, tenant, or customer is added.

The United States Census Bureau Census Geocoder returned exact-address Match results under the
Public_AR_Current benchmark for the five parent-campus addresses. These points are official Census
street-range interpolation/address locators only. They are never parcel, cadastral, campus, building,
project, or construction boundaries; building or project footprints; entrances; survey positions;
site centroids; or point-in-boundary evidence. Numeric horizontal uncertainty is unavailable and is
preserved as unknown. No map tiles or imagery are included.

The current NTT address at 2060 Lookout Drive controls its locator while the conflicting Texas TDLR
address at 2008 Lookout Drive remains disclosed. The QTS 2143 Hands Mill Highway address is scoped
only to the parent York campus, never Building 1.

United States Census Bureau, Census Geocoder Public_AR_Current; compact factual address-match
results are treated as public-domain U.S. government data.

The fixed cohort lifecycle/status cutoff is 2026-08-20. The Census geometry and its identity use were
accepted on 2026-08-23; they do not update cohort lifecycle state. For preview compatibility,
`reviewed_at` remains an alias for the lifecycle cutoff; the manifest and selection report separately
expose `geometry_identity_reviewed_at`.

The artifact is deterministic and rebuildable in a clean clone from 81 manifest-bound portable inputs
plus the byte-frozen v0.11 artifact. Ignored v97 and v14 payloads are optional, complete, all-or-nothing
hydrated cross-checks, not build dependencies. All five new rows remain
independent_imagery_verification=false.

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
