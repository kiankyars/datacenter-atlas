# Verified Construction Core v0.2 preview

This tracked preview contains **11 physical sites** and
**12 linked projects** selected from `2026-07-22-open-seed-v97`.
Every selected project has a physical-status observation no more than 90 days
old at the 2026-08-20 review date. 3 project rows carry official
parcel or surveyed boundary geometry; this describes the geometry attached to the row, not a claim
that construction occupies the entire parcel. The other 9 use explicitly labelled
site-, parcel-, address-, or first-party campus-location points with their precision limits preserved.
Locality centroids and model-only lifecycle states fail the selector.

This is **not** the final Verified Construction Core v1. It does not change the historical Atlas
`construction_verified=false` field, infer a continuously current state, claim independent imagery
verification, or claim completeness. The final release remains blocked at
11/100 sites,
8/40 countries, and
8/50 non-US sites.

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

Workload values remain evidence-linked source classifications, not proof of a running workload.
In particular, the Edged ORD01-2 and AVAIO Taurus disclosures describe intended or purpose-built
workloads; their fuller scope guardrails remain in the pinned source records. Role strings are
inherited from the source release, but v0.2 does not yet publish dedicated evidence identifiers for
each owner, operator, user, tenant, or customer role.

The preview validates from a public clean clone. Rebuilding it still requires the locally hydrated
v97 payload, so clean-clone rebuildability is an explicit failed final-release gate rather than an
implied capability.
