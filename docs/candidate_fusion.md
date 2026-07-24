# Candidate-fusion review lane

The candidate-fusion lane is an immutable review-ordering index over the OSM Planet structural
construction shortlist. It does not create atlas entities, merge records, or infer data-centre
identity, lifecycle, operating status, type, workload, capacity, power, or energy.

## Source-root rules

Every spatial relationship remains an opportunity rather than corroboration:

- Atlas references whose source family is OpenStreetMap or OSM-derived PNNL IM3 are labelled
  `shared_osm_root` and never counted as independent.
- A different upstream root, such as Wikidata or UVA DC-Sense, is labelled
  `distinct_source_root_opportunity`. The label does not establish that the underlying observation
  was independently authored.
- Overture records containing any OpenStreetMap source are conservatively treated as shared-root,
  even if another source also appears on the same record.
- Google Open Buildings Temporal and the Sentinel review pipeline both use Copernicus Sentinel-2.
  They collapse to one imagery root rather than two evidence families.
- A satellite queue entry or successfully selected scene pair is operational review state, not
  visible-change evidence. Only an explicit analyst-retained review is surfaced as a follow-up, and
  that review still confirms no identity or lifecycle state.

The Planet materializer excluded 126 exact typed OSM identities before shortlisting. Fusion checks
exact typed identities again and found zero inside the shortlist, as expected.

## Spatial contracts

The global Atlas lane indexes coordinate-bearing campus, facility, and project rows only. A link is
created when the Atlas point is inside a structural polygon or no more than 5 km from its boundary.
The referenced status remains explicitly scoped to the Atlas reference entity; it is not copied to
the structural candidate.

The Overture Memphis pilot uses feature-bounds overlap only, not polygon identity. The Open
Buildings Egypt pilot uses candidate-bounds versus bounded-AOI overlap only. GDELT's three retained
manual-triage leads have no pinned geometry, so the lane records their coverage but creates no
spatial links.

The output excludes the 88,127 Planet candidates with no configured link. This is an output-size and
review-focus choice, not evidence against those candidates.

## Reproduction

From `datacenter_atlas/`'s parent directory:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 datacenter_atlas/scripts/build_candidate_fusion.py \
  --definition datacenter_atlas/sources/candidate-fusion-2026-07-18-osm-planet-v13.json \
  --output datacenter_atlas/candidate_fusion/2026-07-18-osm-planet-priority-v13
```

The builder refuses an existing destination. To validate hashes, upstream bundles, all terminal
satellite catalog outputs, and byte-for-byte reconstruction offline:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 datacenter_atlas/scripts/build_candidate_fusion.py \
  --definition datacenter_atlas/sources/candidate-fusion-2026-07-18-osm-planet-v13.json \
  --output datacenter_atlas/candidate_fusion/2026-07-18-osm-planet-priority-v13 \
  --validate-only
```

## Pinned v13 result

The v13 bundle preserves the 102,451-row structural shortlist and 14,324-row opportunity output.
It contains 76,028 Atlas proximity links: 68,651 shared OSM-root links and 7,377 distinct-root
opportunities. The 88,127 unlinked structural rows remain outside the fusion output, and the 126
exact typed OSM identities remain excluded upstream.

The frozen catalog input contains the same 6,830 mutually exclusive queue jobs. Active contributes
65 complete and nine no-scene jobs; proposed contributes 16 complete and four no-scene jobs; and
the sole cumulative Unknown015 checkpoint contributes 1,308 complete, 42 no-scene, 5,386 pending,
and zero failed jobs. Unknown001 through Unknown014 are historical overlapping checkpoints and are
not added. Across the 24,419 queue-AOI links, the recomputed catalog states are 5,352 complete, 295
no-scene, and 18,772 pending. These are candidate-AOI links, not queue-job or site counts.

V13 pins 43 unique historical algorithm-v1 report/review pairs: seven active, one proposed, 23 frozen Unknown010 reviews,
six Unknown013 reviews, and six Unknown015 reviews. The Unknown013 set retains Meta Los Lunas
(`satq-a1b14d7a9df2a0937106b63e`) and Google Thornton
(`satq-718ecc6958a13cc59ccf71b9`) only for site-aligned manual follow-up. It rejects the Microsoft
Data Center 2, Amazon IAD131, Iceland M05, and Vantage WA12 masks for site promotion. The full
Unknown015 set retains Meta Eagle Mountain and QTS NAL 2 DC2, while rejecting Microsoft Iowa,
Amazon IAD125, CyrusOne PHX7, and the low-coverage Argentine OSM control. The full decision
inventory is 12 retain and 31 reject. Nine retained reviews overlap 28 candidates through 33 links;
24 rejected reviews overlap 122 candidates through 130 links. The other 24,256
queue-AOI links have no analyst review. Review links can fan out, so links, decisions, candidates,
and sites are four different units.

These labels describe the historical v1 processor only. They do not calibrate the current v2
processor. Two active inputs, queue positions 27 and 60, used clipped selected-asset coverage; a
current calibration requires reprocessing and re-reviewing all 43 inputs, not deleting two rows.

The priority tiers are 28 retained-visible-change follow-ups, 1,037 distinct-source-root
opportunities, and 13,259 shared-root or queue opportunities. They remain review heuristics rather
than probabilities or evidence of identity, lifecycle, type, workload, capacity, power, or energy.
No rows are merged or imported, and no unique physical-site count is computed.

The v13 definition pins Unknown015 manifest
`97a98c2f1de96cd9d9caa8abb31e0b2084b5b00de89f11ad3b3b0df54fe863c8` as the sole cumulative
unknown batch. The v13 manifest SHA-256 is
`12fc7517e5fdb4e00c2a7e59c069d868801ac87ecbc8c0237433b65e51ab9cc9`; the definition SHA-256 is
`63b02b886c83e6b2d9de739f0acb85a566f03d4338796b2a546ddc34cbd3de33`; the JSONL SHA-256 is
`aa4204a2cbd865dd3bb6f9bbb249584f2d314882bfab397553f36807f0636f60`; the CSV SHA-256 is
`5f5fe534daaefc763961f3ec8302c6ce240d78b62ef94b87d207cba9c1efbf2b`; and the coverage SHA-256 is
`c05f3eabf7afa0165d3fa2f9fbba3a3051ce88d2e7aed3bf46fdd8967e2942bf`. The frozen directory is
mode `0555` and all seven files are `0444`.

## Pinned v8 result

The v8 bundle preserves the same 102,451-row structural shortlist and 14,324-row opportunity
output as v7. It contains 76,028 Atlas proximity links across all 14,324 output candidates: 68,651
shared OSM-root links and 7,377 distinct-root opportunities. The 88,127 unlinked structural rows
remain outside the fusion output, and the 126 exact typed OSM identities remain excluded upstream.

The frozen catalog input contains 6,830 mutually exclusive jobs across the active, proposed, and
unknown priority lanes: 805 completed scene pairs, 39 no-scene outcomes, zero failures, and 5,986
pending jobs. `unknown-007` is the sole cumulative unknown-lifecycle checkpoint, with 724 completed,
26 no-scene, zero failed, and 5,986 pending jobs. It replaces unknown-001 through unknown-006; none
of those historical checkpoint counts or reviews is added to v8. Active contributes 65 completed
and nine no-scene jobs, while proposed contributes 16 completed and four no-scene jobs. Once pinned
here, unknown-007 is frozen and must not be resumed or revised.

Across the 24,419 queue-AOI opportunity links and 5,795 linked candidates, catalog states appear on
3,172 completed links, 210 no-scene links, and 21,037 pending links. These are links, not job or site
counts.

V8 pins 21 unique analyst report/review pairs: all 19 current unknown-007 reviews plus the active
and proposed controls exactly once. The four new unknown reviews are rejection controls for queue
IDs `satq-19ba8a09e793d8f73ba71804`, `satq-584c2da9dd872dbb30dbe70f`,
`satq-6cb90d5fbd84d2a283128423`, and `satq-b4c7c51913e4f80878b9aca7`. Hashes, queue entities,
supported decisions, report claim flags, and the complete no-claim review scope are validated rather
than inferred from list length. The input decisions comprise six retained manual follow-ups and 15
rejected masks. Five retained and 11 rejected reviews intersect at least one structural candidate;
their overlaps produce eight retained links and 59 rejected links across five and 52 candidates
respectively. The remaining 24,352 queue links are not analyst reviewed.

Only five candidates receive the top retained-change follow-up tier. The complete tiers remain five
analyst-retained visible-change AOI follow-ups, 1,037 distinct-root opportunities, and 13,282
shared-root or queue opportunities. They remain review heuristics, not probabilities or evidence
of identity, lifecycle, type, workload, capacity, power, or energy. No rows are merged or imported,
and no unique physical-site count is computed.

The v8 manifest SHA-256 is
`487ec311100fac7558bf92fdf9c1ea46dfd0311e158e46272f8cab1e50c82b87`. The definition SHA-256 is
`bb9bf94a1faf1a51b342c46ce587f6a6baac37fbdd8f1b69070393340d6c09bb`; the JSONL SHA-256 is
`58c9acc4dc6cd6cc85fe646f49cf438cbe42dac836820ebac5f8136ca3b85867`; the CSV SHA-256 is
`66c07d4e7fda1ed431db2f4742f8bbfb9c1151a0a11faffd787da25f99762508`; and the coverage SHA-256 is
`f9065629c3dd8cb2c7d2bb6bc2252c11fc38176e388a057001cf2394c4663ce8`.

## Pinned v7 result

The v7 bundle preserves the same 102,451-row structural shortlist and 14,324-row opportunity
output as v6. It contains 76,028 Atlas proximity links across all 14,324 output candidates: 68,651
shared OSM-root links and 7,377 distinct-root opportunities. The 88,127 unlinked structural rows
remain outside the fusion output, and the 126 exact typed OSM identities remain excluded upstream.

The frozen catalog input contains 6,830 mutually exclusive jobs across the active, proposed, and
unknown priority lanes: 707 completed scene pairs, 37 no-scene outcomes, zero failures, and 6,086
pending jobs. `unknown-006` is the sole cumulative unknown-lifecycle checkpoint, with 626 completed,
24 no-scene, zero failed, and 6,086 pending jobs. It replaces unknown-001 through unknown-005; none
of those historical checkpoint counts or reviews is added to v7. Active contributes 65 completed
and nine no-scene jobs, while proposed contributes 16 completed and four no-scene jobs. Once pinned
here, unknown-006 is frozen and must not be resumed or revised.

Across the 24,419 queue-AOI opportunity links and 5,795 linked candidates, catalog states appear on
2,786 completed links, 202 no-scene links, and 21,431 pending links. These are links, not job or site
counts.

V7 pins 17 unique analyst report/review pairs: all 15 current unknown-006 reviews plus the active
and proposed controls exactly once. Hashes, queue entities, supported decisions, report claim
flags, and the complete no-claim review scope are validated rather than inferred from list length.
The input decisions comprise six retained manual follow-ups and 11 rejected masks. Five retained
and eight rejected reviews intersect at least one structural candidate; their overlaps produce
eight retained links and 43 rejected links across five and 36 candidates respectively. The
remaining 24,368 queue links are not analyst reviewed.

Only five candidates receive the top retained-change follow-up tier. The complete tiers remain five
analyst-retained visible-change AOI follow-ups, 1,037 distinct-root opportunities, and 13,282
shared-root or queue opportunities. They remain review heuristics, not probabilities or evidence
of identity, lifecycle, type, workload, capacity, power, or energy. No rows are merged or imported,
and no unique physical-site count is computed.

The v7 manifest SHA-256 is
`c009f8291bdfd56e18e473dfa088da52d9a5748379b252a44c59f87a664613fa`. The definition SHA-256 is
`13ddff6239acb89e6a51c4abb9c15acb39310a2bd7134b03a6b464ef178149bf`; the JSONL SHA-256 is
`6c701dba5308dbc923cf0d047441d5dcc7492a49d161577a5e3d070016cc5457`; the CSV SHA-256 is
`66c07d4e7fda1ed431db2f4742f8bbfb9c1151a0a11faffd787da25f99762508`; and the coverage SHA-256 is
`23119d02476867049e9b07f6aa2494c7a8a45d1a6ef5688ba4f37244591dd45e`.

## Pinned v6 result

The v6 bundle preserves the same 102,451-row structural shortlist and 14,324-row opportunity
output as v5. It contains 76,028 Atlas proximity links across all 14,324 output candidates: 68,651
shared OSM-root links and 7,377 distinct-root opportunities. The 88,127 unlinked structural rows
remain outside the fusion output, and the 126 exact typed OSM identities remain excluded upstream.

The frozen catalog input contains 6,830 mutually exclusive jobs across the active, proposed, and
unknown priority lanes: 611 completed scene pairs, 33 no-scene outcomes, zero failures, and 6,186
pending jobs. `unknown-005` is the sole cumulative unknown-lifecycle checkpoint, with 530 completed,
20 no-scene, zero failed, and 6,186 pending jobs. It replaces unknown-002, unknown-003, and
unknown-004; their counts are never added to it. Active contributes 65 completed and nine no-scene
jobs, while proposed contributes 16 completed and four no-scene jobs.

Across the 24,419 queue-AOI opportunity links and 5,795 linked candidates, catalog states appear on
2,369 completed links, 177 no-scene links, and 21,873 pending links. These are links, not job or site
counts.

V6 pins 13 unique analyst report/review pairs: all 11 canonical unknown-005 reviews plus the active
and proposed controls exactly once. Hashes, queue entities, supported decisions, report claim flags,
and the complete no-claim review scope are validated rather than inferred from the list length. The
input decisions comprise six retained manual follow-ups and seven rejected masks. Five retained and
six rejected reviews intersect at least one structural candidate; their overlaps produce eight
retained links and 30 rejected links across five and 23 candidates respectively. The remaining
24,381 queue links are not analyst reviewed.

Only five candidates receive the top retained-change follow-up tier. The complete tiers remain five
analyst-retained visible-change AOI follow-ups, 1,037 distinct-root opportunities, and 13,282
shared-root or queue opportunities. They remain review heuristics, not probabilities or evidence of
identity, lifecycle, type, workload, capacity, power, or energy. No rows are merged or imported, and
the unique-site count remains null.

The v6 manifest SHA-256 is
`8cacc1e33174682736357c0a931b8cd521da1da5d70945a75d38555a7da8bdcb`. The definition SHA-256 is
`e1be7cce1b23aa86c4632d184abf83f85af7b4f1d859a9991b868b165c38c568`; the JSONL SHA-256 is
`f91e283de3bde4000c2dde6fae81533c6c1ec753edb47258bd16e176bd752336`; the CSV SHA-256 is
`66c07d4e7fda1ed431db2f4742f8bbfb9c1151a0a11faffd787da25f99762508`; and the coverage SHA-256 is
`c35a7dc4841f5622cf30f2ce01a7b4aa379fd9d09aa541d4e587ff29e6636935`.

## Pinned v5 result

The v5 bundle examined 102,451 structural candidates and retained 14,324 with at least one fusion
opportunity:

- 76,028 Atlas proximity links across 14,324 candidates: 68,651 shared OSM-root links and 7,377
  distinct-root opportunities;
- zero exact typed OSM identity links in the shortlist, in addition to the 126 exact identities
  excluded before fusion;
- 24,419 Sentinel queue-AOI links across 5,795 candidates, including 1,294 links with a completed
  catalog pair, 91 with no suitable scene, and 23,034 pending in the pinned cumulative batches;
- three retained analyst reviews with five candidate-AOI overlap links: two apiece for EAT12 and
  EAT03 plus one for the AWS us-west-2 container follow-up;
- three rejected reviews with eleven overlap links in total: eight for the QTS Hillsboro negative
  control, one for OSM way 775412067, and two for OSM way 1505120011;
- zero Overture bounds overlaps in the pinned 96-footprint Memphis pilot;
- zero Open Buildings AOI overlaps in the pinned three-signal Egypt pilot; and
- three GDELT retained leads registered but zero spatially linked because none has pinned geometry.

Only the five retained-result overlaps receive the top follow-up tier. EAT03's Atlas identity remains
shared with the PNNL/OpenStreetMap root, and the imagery follow-up creates no lifecycle claim. The
tiers contain five analyst-retained-visible-change-AOI-overlap follow-ups, 1,037 distinct-root
opportunities, and 13,282 shared-root or queue opportunities. These are review-ordering categories,
not probabilities. The coverage artifact separately reports links, candidates, and distinct reviews
for `retained_visible_change_aoi_followup` and `rejected_for_site_promotion`.

The manifest SHA-256 is
`9c841495f1a1e51766ab17c41796c8c298c6286e7a8f6527b0f0914e85ce6d6c`. The definition SHA-256 is
`4e60a4733c51e06a44f3ce09b13a66863c1d2c0a45c1f3ab7735bc015cbecc8e`; the JSONL SHA-256 is
`c08ecc125c0c6b2c59366cb258ec865e98a7d84905d11509ef8dd2d24827b148`; the CSV SHA-256 is
`5b19bfb676194b0d2d07f31e1a10bed1ed74f7204909a8664979fa9917073e43`; and the coverage SHA-256 is
`28e34d0d20ed94043671ddb04d7c8c0aa324ff650b5f32bf3f5de9ab5a262b8e`.

The historical v5 unknown-lifecycle input is the frozen `unknown-002` cumulative continuation: 242 completed
scene pairs, eight no-scene outcomes, zero failed jobs, and 6,486 pending jobs. It supersedes
`unknown-001` for current catalog accounting and is not additive to it. The v4 bundle remains an
immutable historical checkpoint. V5 also remains immutable; v6 does not revise either bundle.
