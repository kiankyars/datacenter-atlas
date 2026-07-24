# Cross-release resolution

The Scrutica discovery release and the open ODbL/CC0 release remain separate license partitions.
Their arithmetic federation therefore cannot answer how many unique physical sites they represent.
The cross-release resolution lane provides a narrower, auditable bridge without changing that
boundary.

`scripts/build_cross_release_resolution.py` hash-validates every file in both child releases, opens
their bound `atlas.sqlite` databases in immutable read-only mode, and compares the current campus
and facility records, then revalidates both complete children after querying and before publication.
It writes an atomic review bundle containing:

- JSON and CSV candidate links with stable entity and evidence IDs from both releases;
- great-circle distance and explicit name, address, organization, geometry, and country signals;
- an exact typed OpenStreetMap identity signal when stable keys or upstream URLs resolve to the same
  node, way, or relation;
- the upstream provenance root for each record and an independence flag;
- exact checkpoints for both child manifests and databases; and
- the unmodified attribution text from each child.

Candidate rows necessarily reproduce selected child identifiers, names, source-family labels, and
provenance fields; they do not copy either child database. Evidence IDs remain pointers into their
respective child records, and every reproduced field remains subject to that child's rights and
attribution. The scope contract records these facts explicitly.

The default spatial window is 5 km. Same-kind rows can be suggested as `same_site_candidate` only
within 1.5 km and above the published score gate. Campus/facility pairs can be suggested as
`part_of_candidate` only within 3 km and above their separate gate. Everything else inside the
window remains `nearby_only`. These labels are review priorities, not identity adjudications.
An exact typed OpenStreetMap identity is still emitted when coordinates disagree by more than 5 km;
it remains `nearby_only` so the location conflict is not hidden behind the identity key.

In particular, a Scrutica row derived from OpenStreetMap and a direct OpenStreetMap row share the
same provenance root. Their link is retained for deduplication review but is explicitly not
independent corroboration. No link changes either child, creates a facility, confirms a status, or
contributes to a unique-site count.

```sh
python3 scripts/build_cross_release_resolution.py \
  --left-release releases/scrutica-2026-07-18 \
  --right-release releases/2026-07-18-global-open-v3 \
  --left-label scrutica-2026-07-18 \
  --right-label global-open-v3 \
  --output-dir cross_release_resolution/scrutica-open-2026-07-18 \
  --generated-at <canonical-UTC-timestamp>
```

The bundle is intentionally excluded from federated entity totals. A reviewed decision layer can
later accept or reject individual links, but any published deduplicated count must also define the
campus/facility/building/phase ontology and retain the decision evidence.

## Checked Scrutica/open crosswalk

The checked `cross_release_resolution/scrutica-global-open-v3-v3/` bundle compares 3,540
coordinate-bearing Scrutica rows with 6,771 global-open campus/facility rows. It emits 62,896
advisory links: 2,737 `same_site_candidate`, 92 `part_of_candidate`, and 60,067 `nearby_only`.
Exactly 1,351 links share a typed OpenStreetMap identity and all 1,351 share the OpenStreetMap
upstream root. Across the elevated suggestions, 423 same-site and 26 part-of links are
independent-source opportunities; the remaining 2,380 share an upstream root. Proximity and source
independence do not establish identity or corroborate a lifecycle, type, or power claim. The
bundle's manifest SHA-256 is
`31601916476b805205392f92b3952583f543ff4302e425bbf850145a87b8e0d5`.

## Checked scale pilot

The checked `cross_release_resolution/osm-fuzzy-global-open-v3-pilot-v2/` bundle exercised the gate on
6,130 review-only fuzzy OSM records and 6,771 coordinate-bearing campus/facility records in
global-open-v3. It emitted 5,740 links: 84 `same_site_candidate`, five `part_of_candidate`, and
5,651 `nearby_only`. Of those, 4,758 share the OpenStreetMap provenance root; 982 are spatial links
to UVA or Wikidata records and are merely independent-source *opportunities*, not confirmations of
the fuzzy record's data-centre identity. The bundle revalidates offline; its manifest SHA-256 is
`4643a6486db989d2534f17209aa8d9688e991c0201a536b515cc51f87063f88f`.
