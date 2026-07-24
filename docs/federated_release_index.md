# Federated release index

The federated index makes separately licensed Data Center Atlas releases discoverable together
without constructing a combined dataset. It contains references, exact checkpoints, child
attribution text, and descriptive metadata only. It does not copy child data files, merge entities,
collapse source-family labels across releases, perform cross-source deduplication, or produce a
unique-physical-site count.

This is the publication boundary for compatible, redistribution-cleared children. Only completed,
closed, hash-pinned releases with an evidenced reuse basis can enter the current public index.

The checked `federated_indexes/2026-07-19-public-open-v9` index is the current publication-safe
view. It references open-seed v20, global-open-v3, and OSM fuzzy-review-v2. Its arithmetic total of
15,707 source-scoped rows is split into 9,577 non-review and 6,130 review-only rows. Its 6,401
construction-pipeline rows are separately labeled as 271 non-review records and 6,130 review-only
candidates. It also accounts for 13,195 evidence records, 67 release-scoped source-family entries,
1,178 capacity estimates, and 100,409 advisory resolution candidates. It makes no unique-site
claim.

The v9 federation definition SHA-256 is
`3c7a9b13cda5ffd5cc4791b47f7f93266d441c37a10cd44883a7caff15b1d9f1`; the published manifest
SHA-256 is `9dee9fc48ce8dd4d729bbd45fec7d976f79af041894ecb1ef5a9401f7f4f04c5`; and the exact
`federated-index.json` SHA-256 is
`600b34d8807fa06b2ea2e098c39f72d2299a8a485ae08a41b66c9b334bdc4cb1`. The frozen open-seed
v20 child has definition SHA-256
`099f1f519cc7440fa160ed6db7220d91562ae8b1cea6c1ef1305eefbbb5319fd` and manifest SHA-256
`e45aeeddc2d450a9faebf9f8919e3726dadf2547c95a864c395c75c95302c456`.

Public-open v5 through v8 remain frozen historical indexes. The prior v8 view references
open-seed v13, global-open-v3, and OSM fuzzy-review-v2 and totals 15,619 source-scoped rows, 9,489
non-review rows, 6,130 review-only rows, 6,355 construction-pipeline rows, 13,153 evidence records,
44 release-scoped source-family entries, and 1,148 capacity estimates. Its definition, manifest,
and index SHA-256 values remain
`91aed1938136a9bfd6432745cffcd1dfe55cfe5c1a99d72f2998d5ff63c9bbf0`,
`0db9b8d8ee48c63eb9d95054af42dccc38133be417da5d51cc41b220d0d73f48`, and
`75737e6175f4de03f84e9b0cead12e92cf5fcdfa9e59a85ba845bd0a7fa60bd4`, respectively. Its
open-seed v13 child remains pinned by definition SHA-256
`5b62d3e69e8ae09de70fc7046318d36054e4a264d00f606efc67fa88a89bd3be` and manifest SHA-256
`3aace8621b42d4026a534afca64de9181af21e98c581867a9bebf8ec5bdf96f7`. These historical indexes
are not current because their open-seed children predate later official-source records; no child
was overwritten.

The separately retained `federated_indexes/2026-07-18-four-layer-v2` artifact also references the
Scrutica child and totals 19,625 source-scoped rows. It is a reproducible local research view, not
current public output. The [PeeringDB assessment](peeringdb.md) found 1,548 PeeringDB-derived
Scrutica rows with no recorded permission or upstream license basis. The whole mixed-rights
Scrutica child is therefore quarantined until every upstream family has an evidenced reuse basis.

## Definition

Create a hash-pinned JSON definition. Relative `release_path` values are resolved from the
definition file's directory; these local build paths are never emitted. `reference` is the public
relative path or HTTPS URL that consumers should follow.

```json
{
  "schema_version": 1,
  "generated_at": "2026-07-18T22:00:00Z",
  "children": [
    {
      "release_id": "global-open-v3",
      "release_path": "../releases/2026-07-18-global-open-v3",
      "reference": "../2026-07-18-global-open-v3/",
      "expected_manifest_sha256": "<exact manifest.json SHA-256>",
      "license_expression": "ODbL-1.0",
      "rights_notice": "ODbL and child source attributions apply only to this child."
    },
    {
      "release_id": "osm-fuzzy-review-v2",
      "release_path": "../releases/2026-07-18-osm-fuzzy-review-v2",
      "reference": "../2026-07-18-osm-fuzzy-review-v2/",
      "expected_manifest_sha256": "<exact manifest.json SHA-256>",
      "license_expression": "ODbL-1.0 with a Public Domain boundary input",
      "rights_notice": "This is a review-only ODbL candidate layer, not a confirmed facility list."
    }
  ]
}
```

At least two distinct child directories, release IDs, and references are required. Each exact child
manifest hash must be declared before the build, so an updated release cannot silently replace the
intended version.

```sh
python3 scripts/build_federated_release_index.py \
  --definition federation-definition.json \
  --output-dir releases/federated-2026-07-18
```

## Child validation and rights

Every child must be a canonical `datacenter-atlas-release-v1` bundle. Before indexing, the builder:

- verifies the definition's exact manifest SHA-256;
- requires the manifest's closed file set and verifies every byte count and SHA-256;
- rejects symlinks, directories, unsafe filenames, and unlisted files;
- reconciles `entities.csv` row and kind counts with the manifest;
- reconciles `evidence.csv` row count and source families with the manifest;
- derives the exact source-license set from the manifest-bound evidence CSV;
- requires and hash-binds `ATTRIBUTION.txt` and `source_inputs.json`.

If a child manifest declares `review_only: true`, that scope remains machine-readable in the
descriptor. Fuzzy-review shortlist and excluded-row counts, when present, must be non-negative,
must occur together, and must sum exactly to the child's entity count. A false review marker,
partial pair, or mismatched count fails closed.

Each release descriptor retains its own license expression, rights notice, source-license set,
exact attribution text/checkpoint, source families, child manifest checkpoint, and complete child
file inventory. There is deliberately no federation-level license expression or combined
attribution: reuse obligations remain attached to the child that supplied them.

## Counts and artifacts

The only federation totals are arithmetic sums of child release counts:

- release bundles;
- release-scoped source-family entries, without collapsing equal labels;
- source-scoped entity records;
- review-only and non-review source-scoped entity records as separate subtotals;
- evidence, capacity, construction-pipeline, and resolution-candidate records; and
- review-only and non-review construction-pipeline records as separate subtotals.

These totals can double-count the same real facility across children or versions. Review candidates
are included only in explicitly labeled review-only subtotals; they are not hidden inside the
non-review entity or construction totals. Older valid index bundles without the additive
construction split remain offline-valid, but new builds always emit it. The index always sets
`unique_physical_sites` to `null` and states that no
cross-source deduplication occurred.

The immutable output directory contains exactly:

- `federated-index.json`: sorted child descriptors, boundary policy, and arithmetic counts;
- `manifest.json`: exact definition and index checkpoints;
- `manifest.sha256`: SHA-256 of the exact manifest bytes.

`validate_federated_release_index(path)` validates the closed index bundle. Passing an exact
`child_release_paths` mapping revalidates every external child and compares its newly derived
descriptor with the published one. First publication stages all three files, validates them, and
performs one directory rename. An existing directory is accepted only when it is valid and all
three files are byte-identical; invalid or different output is refused and left untouched.
