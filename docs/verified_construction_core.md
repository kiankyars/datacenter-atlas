# Verified Construction Core

The long-term product target is a compact, public cohort of 100 physical data-centre sites with
linked active construction projects, precise geometry, current evidence, typed power semantics,
and reviewable imagery outcomes. The current artifact is deliberately labelled
[`v0.6 preview`](../verified_construction_core/2026-08-20-preview-v0.6/README.md), because the
available evidence does not yet support that final claim. The previous
[`v0.5 preview`](../verified_construction_core/2026-08-20-preview-v0.5/README.md),
[`v0.4 preview`](../verified_construction_core/2026-08-20-preview-v0.4/README.md),
[`v0.3 preview`](../verified_construction_core/2026-08-20-preview-v0.3/README.md),
[`v0.2 preview`](../verified_construction_core/2026-08-20-preview-v0.2/README.md) and
[`v0.1 preview`](../verified_construction_core/2026-08-19-preview-v0.1/README.md) remain
byte-frozen and hash-validated rather than being overwritten.

## Preview scope

The preview selects 29 projects attached to 26 source-scoped campus sites in 17 countries from
`2026-07-22-open-seed-v97`. Every project has:

- a physical-status observation no more than 90 days old on the fixed 2026-08-20 review date;
- an authoritative physical-status method and an explicit evidence row;
- one reviewed project-to-campus identity link;
- a pinned source record and geometry-evidence key; and
- an official boundary or a source-specific site/address locator with its precision limit.

CoreSite DE3 and Scala SFORPF01 have official parcel or surveyed project polygons. Verne Mäntsälä
uses the exact municipal cadastral polygon of its explicitly linked parent campus; that polygon is
not presented as the footprint of the current 70 MW development. Green Mountain Undheim uses the
deterministic union of official Kartverket parcels 1121-46/316, /317, and /319. It is the approved
project-site parcel boundary, not either data-hall footprint or the observed construction extent.
Fifteen project rows use points and are labelled by their actual scope: shared-campus reference,
facility reference,
same-parcel infrastructure reference, parcel reference, official address, or first-party campus
location. They are not silently promoted to building footprints or site boundaries.

The v0.6 points include the coordinate printed in AdaniConneX/Pune Data Center Limited's PNQ04
compliance report, accepted only as a `project_locator`; the Hong Kong Lands Department HKG09
address result transformed through its official HK80-to-WGS84 service; and Kartverket's verified
Østre Aker vei 24C address point for Skygard OSL1. The Goodman and Skygard points are
`campus_locator` records, not project or building footprints. Kvandal uses the exact frozen current
Kartverket boundary of parcel 1806-10/760 only as a campus locator after a separate NVE identity
bridge. It is not the 25 MW Data Center 1 footprint, the later 75 MW project footprint, or proof that
the one parcel is the complete Nscale campus.

atNorth ICE02 Phase 2, QScale Q01 Building B, Green ZRH1 DC4, The Barn Saline, Microsoft Mount
Pleasant's second facility, Amazon Salem's active buildout, and STT Jakarta 3, 5, and 6 are nine
project rows using contributor-mapped OSM polygon locators (seven distinct polygons) under a separate authority model. Each is accepted only as a
`community_mapped`
`campus_locator`; none is counted as an official boundary, project/phase footprint, construction
extent, lifecycle observation, or imagery result. The selected geometry locates the named campus,
not necessarily the current building project. QScale retains one reported 60 MW design-stage
critical-IT observation. Saline's 1,400 MW contracted campus grid connection and modeled annual
energy range remain pinned in the bridge for provenance but are not promoted to project power or
measured consumption. Campus operating models likewise do not become project claims. The three
STT rows deliberately share the same STT Jakarta 1 OSM polygon as a campus locator; that polygon is
not any Jakarta 3/5/6 footprint.

The review contract distinguishes `direct_geometry` from `coordinates_to_point` and records
whether geometry comes from the project or its parent campus. Coordinate serialization adds no
precision. The maincubes BER02, AVAIO Taurus, and KAO KLON-03 points retain unknown horizontal
accuracy. Scala Huechuraba and Lampa use official Chilean environmental-review representative
points with conservative 50 metre analyst envelopes; neither is presented as a footprint.

The project status field is `last_observed_physical_status`, not an inferred current state. The
preview leaves `independent_imagery_verification=false` for every row. Eight inherited projects
have a non-default satellite-review outcome, but those reviews create no lifecycle claim. Six are portable
identity-bound records; two preserve an identity mapping extracted from exact local hash-bound
lineage that is not independently available in a clean clone. Saline retains only its tracked v57
visible-change follow-up verdict; an unsealed later review is not published as project evidence.
Microsoft and Amazon retain uncertain v57 outcomes. BER02's later conflicting blind verdict and
KAO's later conflicting verdict remain unsuperseded rather than being resolved in favor of either
judgment.

Undheim adds one explicit `publisher_contractor_drone_context` record linked to Backe's project
page. It redistributes no image bytes and is not a blind, satellite, or independent review. The
validator forbids using it for geometry, status, capacity, progress, or building count.

## Files and semantics

- `projects.csv` preserves project-level status, geometry source entity, derivation, method and
  scope, coordinate precision, source URLs, typed power observations, and explicit
  unknown/not-estimated reasons.
- `sites.csv` groups the 29 selected projects into 26 physical-site keys without claiming
  global cross-source deduplication.
- `evidence.csv` is the closed set of 63 status, geometry, operating-model, workload, role, and
  typed-metric evidence rows referenced by the cohort.
- `sites.geojson` and the dependency-free `map.html` expose the same 26 site IDs.
- `schema.json` defines CSV fields, logical types, keys, embedded evidence references, GeoJSON
  geometry equality, and the map dependency in machine-readable form.
- `selection-report.json` accounts for all 531 source pipeline rows and records every final gate.
  It also carries the exact non-default imagery-review provenance and unresolved conflicts.
- `manifest.json` and `manifest.sha256` bind the complete preview inventory.

## Version policy

Each preview is a coherent frozen snapshot, not a separate pile of data that must be added to the
latest CSV. v0.6 inherits all 21 reviewed v0.5 decisions through an exact base contract hash and
adds eight projects across six physical sites; v0.5 inherits all 17 reviewed v0.4 decisions and
adds four reviewed geometry bridges; v0.4 inherits the 15 reviewed v0.3 decisions and adds two;
v0.3 inherits the 12 reviewed v0.2 decisions and adds three. Users normally consume only the latest
preview; the older artifact remains because it proves what the product said at that date and lets a
historical result be audited against the code commit that produced it.

Missing development type, operating model, workload, power, annual energy, PUE, or WUE never
becomes zero. Reported observations preserve metric, stage, units, interval, method, confidence,
and evidence. PUE/WUE stay separate from power; annual energy remains unestimated unless scoped
inputs and assumptions exist.

Workload values are evidence-linked source classifications, not proof of an operating workload.
Every observation has a validator-bound `deployment_scope`; all five current observations are
`intended`. Every published role has a machine-readable evidence ID and relationship scope. Six
intended-operator and two intended-customer claims pass. Four prior CDC/AST owner or operator
strings plus the atNorth, QScale, Microsoft, and Amazon project-operator candidates lack
role-specific evidence, so the current preview clears them and records the exclusions and reasons
instead.

## Validation and rebuild

Validation works in a public clean clone once the generated preview and all manifest-listed inputs
are tracked. v0.6 enumerates 25 portable current-delta inputs, including eight curated source
records, eight geometry bridges, the frozen Kvandal WFS capture, and all eight members of the
Undheim Kartverket capture set:

```sh
uv run python scripts/build_verified_construction_core.py --validate-only
uv run python -m unittest -v tests.test_verified_construction_core
```

A byte-exact rebuild additionally needs the locally hydrated v97 payload and the pinned source
records. The builder refuses to overwrite an existing directory:

```sh
uv run python scripts/build_verified_construction_core.py \
  --output-dir /tmp/verified-construction-core-preview
```

## Final-release gates

The preview cannot be promoted to v1 until it has exactly 100 resolved sites and linked projects,
at least 40 countries, at least 50 non-US sites, no country above 40% of the cohort, a recorded
imagery outcome for every selected project (and therefore every site), a blind 20-row re-review with at least 19 identity/construction
agreements, and a byte-exact clean-clone rebuild from publicly available inputs.

The next research tranche should start with fresh authoritative project rows in countries absent
from this preview, resolve an official parcel/site/address geometry, then execute dated imagery
review where usable scenes exist. Locality/model centroids remain rejected; an official project
representative point is usable only as an explicitly labelled locator with an uncertainty envelope.
Announcement, permit, catalog completion, or automated pixel change alone does not satisfy the
physical-construction gate.
