# Verified Construction Core

The long-term product target is a compact, public cohort of 100 physical data-centre sites with
linked active construction projects, precise geometry, current evidence, typed power semantics,
and reviewable imagery outcomes. The first checked artifact is deliberately labelled
[`v0.1 preview`](../verified_construction_core/2026-08-19-preview-v0.1/README.md), because the
available evidence does not yet support that final claim.

## Preview scope

The preview selects 9 projects attached to 8 source-scoped campus sites in 6 countries from
`2026-07-22-open-seed-v97`. Every project has:

- a physical-status observation no more than 90 days old on the fixed 2026-08-19 review date;
- an authoritative physical-status method and an explicit evidence row;
- one reviewed project-to-campus identity link;
- a pinned source record and geometry-evidence key; and
- an official boundary or a source-specific site/address locator with its precision limit.

Only CoreSite DE3 and Scala SFORPF01 have official parcel or surveyed project polygons. The other
seven project rows use points and are labelled by their actual scope: shared-campus reference,
facility reference, same-parcel infrastructure reference, parcel reference, or official address.
They are not silently promoted to building footprints or site boundaries.

The project status field is `last_observed_physical_status`, not an inferred current state. The
preview leaves `independent_imagery_verification=false` for every row. Existing satellite reviews
are retained as analyst outcomes and create no lifecycle claim.

## Files and semantics

- `projects.csv` preserves project-level status, geometry method and scope, coordinate precision,
  source URLs, typed power observations, and explicit unknown/not-estimated reasons.
- `sites.csv` groups the nine selected projects into eight physical-site keys without claiming
  global cross-source deduplication.
- `evidence.csv` is the closed set of 23 status, geometry, operating-model, workload, and typed-metric
  evidence rows referenced by the cohort.
- `sites.geojson` and the dependency-free `map.html` expose the same eight site IDs.
- `schema.json` defines CSV fields, logical types, keys, embedded evidence references, GeoJSON
  geometry equality, and the map dependency in machine-readable form.
- `selection-report.json` accounts for all 531 source pipeline rows and records every final gate.
- `manifest.json` and `manifest.sha256` bind the complete preview inventory.

Missing development type, operating model, workload, power, annual energy, PUE, or WUE never
becomes zero. Reported observations preserve metric, stage, units, interval, method, confidence,
and evidence. PUE/WUE stay separate from power; annual energy remains unestimated unless scoped
inputs and assumptions exist.

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
review where usable scenes exist. Announcement, permit, catalog completion, or automated pixel
change alone does not satisfy the physical-construction gate.
