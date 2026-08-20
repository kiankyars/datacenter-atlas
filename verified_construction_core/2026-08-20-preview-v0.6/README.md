# Verified Construction Core v0.6 preview

This tracked preview contains **26 physical sites** and
**29 linked projects** selected from `2026-07-22-open-seed-v97`.
Every selected project has a physical-status observation no more than 90 days
old at the 2026-08-20 review date. 4 project rows carry official
parcel or surveyed boundary geometry; this describes the geometry attached to the row, not a claim
that construction occupies the entire parcel. The other 25 use explicitly labelled
reviewed locators with their precision limits preserved. Nine selected project rows use
contributor-mapped OSM polygon locators (seven distinct polygons), accepted only as campus locators:
they are not official boundaries, project or phase
footprints, construction extents, or lifecycle evidence. Locality centroids and model-only lifecycle
states fail the selector.

The v0.6 delta adds an official PNQ04 project reference point; official Goodman HKG09 and Skygard
OSL1 campus address/reference points; an official current Kvandal parcel used only as a campus
locator; one shared STT Jakarta 1 OSM campus locator for Jakarta 3, 5, and 6; and the official
three-parcel Undheim project-site union. None of those locator geometries is promoted to a current
building footprint. The Undheim parcel union is an official boundary, but still not a claim that
construction fills the parcels.

This is **not** the final Verified Construction Core v1. It does not change the historical Atlas
`construction_verified=false` field, infer a continuously current state, claim independent imagery
verification, or claim completeness. The final release remains blocked at
26/100 sites,
17/40 countries, and
20/50 non-US sites.

Files:

- `sites.csv` and `projects.csv`: the reviewed physical-site/project cohort.
- `sites.geojson` and `map.html`: matching clean-clone-readable map products.
- `evidence.csv`: status, geometry, operating-model, workload, and typed-metric evidence.
- `schema.json`: machine-readable field, relationship, GeoJSON, and map contract.
- `selection-report.json`: accounting for every source pipeline row and every final gate.
- `manifest.json` and `manifest.sha256`: byte and SHA-256 bindings.

Missing power, annual energy, operating model, workload, and development type remain explicit
unknowns; the builder never converts missing values to zero. Existing satellite reviews remain
non-claiming analyst evidence. The selection report binds each non-default imagery outcome to its
exact tracked review source and preserves locally unsealed identity lineage and unadjudicated
conflicts explicitly. Two exact Canadian geometry overlays were reviewed but excluded: one recent
scene was unusable and one usable comparison showed no filtered recent-change component.
Backe-published Undheim contractor drone photography is source-linked context only: no image bytes
are redistributed, no independent imagery review is claimed, and it supports no geometry, status,
capacity, progress, or building-count field.

Every workload observation carries a validator-bound `deployment_scope`; all five selected
observations are `intended`, never operational. `role_claims_json` binds each published role to an
evidence ID and relationship scope. Six intended-operator and two intended-customer claims pass
that gate. Four prior CDC/AST owner or operator strings lacked role-specific evidence, so the preview
clears them and preserves the rejected claims and reasons in the provenance contract rather than
laundering status evidence into role evidence. The same conservative rule clears the atNorth,
QScale, Microsoft Mount Pleasant, and Amazon Salem operator candidates; OSM operator tags, campus
operating models, and branded status evidence are identity context, not project-role proof.

Saline's source-level 1,400 MW contracted grid-load observation and modeled annual-energy range are
retained only in the closed bridge as campus-scoped provenance. They are not promoted to project or
site power or energy, and the modeled range is not measured consumption.

The preview validates from a public clean clone. Rebuilding it still requires the locally hydrated
v97 payload, so clean-clone rebuildability is an explicit failed final-release gate rather than an
implied capability.
