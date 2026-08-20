# Verified Construction Core

The long-term product target is a compact, public cohort of 100 physical data-centre sites with
linked active construction projects, precise geometry, current evidence, typed power semantics,
and reviewable imagery outcomes. The current checked artifact is deliberately labelled
[`v0.2 preview`](../verified_construction_core/2026-08-20-preview-v0.2/README.md), because the
available evidence does not yet support that final claim. The previous
[`v0.1 preview`](../verified_construction_core/2026-08-19-preview-v0.1/README.md) remains
byte-frozen and hash-validated rather than being overwritten.

## Preview scope

The preview selects 12 projects attached to 11 source-scoped campus sites in 8 countries from
`2026-07-22-open-seed-v97`. Every project has:

- a physical-status observation no more than 90 days old on the fixed 2026-08-20 review date;
- an authoritative physical-status method and an explicit evidence row;
- one reviewed project-to-campus identity link;
- a pinned source record and geometry-evidence key; and
- an official boundary or a source-specific site/address locator with its precision limit.

CoreSite DE3 and Scala SFORPF01 have official parcel or surveyed project polygons. Verne Mäntsälä
uses the exact municipal cadastral polygon of its explicitly linked parent campus; that polygon is
not presented as the footprint of the current 70 MW development. The other nine project rows use
points and are labelled by their actual scope: shared-campus reference, facility reference,
same-parcel infrastructure reference, parcel reference, official address, or first-party campus
location. They are not silently promoted to building footprints or site boundaries.

The v0.2 review contract distinguishes `direct_geometry` from `coordinates_to_point` and records
whether geometry comes from the project or its parent campus. Coordinate serialization adds no
precision. The maincubes BER02 and AVAIO Taurus points retain unknown horizontal accuracy.

The project status field is `last_observed_physical_status`, not an inferred current state. The
preview leaves `independent_imagery_verification=false` for every row. Four projects have a
non-default satellite-review outcome, but those reviews create no lifecycle claim. Two are
portable identity-bound records; two preserve an identity mapping extracted from exact local
hash-bound lineage that is not independently available in a clean clone. BER02's later conflicting
blind verdict is retained as unsuperseded rather than resolved in favor of either judgment.

## Files and semantics

- `projects.csv` preserves project-level status, geometry source entity, derivation, method and
  scope, coordinate precision, source URLs, typed power observations, and explicit
  unknown/not-estimated reasons.
- `sites.csv` groups the 12 selected projects into 11 physical-site keys without claiming
  global cross-source deduplication.
- `evidence.csv` is the closed set of 29 status, geometry, operating-model, workload, and typed-metric
  evidence rows referenced by the cohort.
- `sites.geojson` and the dependency-free `map.html` expose the same 11 site IDs.
- `schema.json` defines CSV fields, logical types, keys, embedded evidence references, GeoJSON
  geometry equality, and the map dependency in machine-readable form.
- `selection-report.json` accounts for all 531 source pipeline rows and records every final gate.
  It also carries the exact non-default imagery-review provenance and unresolved conflicts.
- `manifest.json` and `manifest.sha256` bind the complete preview inventory.

## Version policy

Each preview is a coherent frozen snapshot, not a separate pile of data that must be added to the
latest CSV. v0.2 inherits the nine reviewed v0.1 project/site decisions through an exact base
contract hash and adds three new decisions. Users normally consume only the latest preview; the
older artifact remains because it proves what the product said at that date and lets a historical
result be audited against the code commit that produced it.

Missing development type, operating model, workload, power, annual energy, PUE, or WUE never
becomes zero. Reported observations preserve metric, stage, units, interval, method, confidence,
and evidence. PUE/WUE stay separate from power; annual energy remains unestimated unless scoped
inputs and assumptions exist.

Two preview-schema limitations remain explicit. Workload values are evidence-linked source
classifications, not proof of an operating workload: the Edged ORD01-2 and AVAIO Taurus evidence
describes intended or purpose-built workloads, with the complete qualifier retained in each pinned
source record. Role strings are inherited from the source release, but v0.2 does not yet carry a
dedicated evidence identifier for every owner, operator, user, tenant, or customer role. A later
schema revision should promote both qualifiers into machine-readable, validator-bound fields.

## Validation and rebuild

Validation works in a public clean clone because all preview payloads, definitions, and the v97
manifest are tracked:

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
imagery outcome for every site, a blind 20-row re-review with at least 19 identity/construction
agreements, and a byte-exact clean-clone rebuild from publicly available inputs.

The next research tranche should start with fresh authoritative project rows in countries absent
from this preview, resolve an official parcel/site/address geometry, then execute dated imagery
review where usable scenes exist. Representative and locality points remain rejected. Announcement,
permit, catalog completion, or automated pixel change alone does not satisfy the
physical-construction gate.
