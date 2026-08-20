# Active-lane change-selection checkpoints

These three canonical JSON files are immutable exclusion inputs for the legacy
single-asset v2 batch runner. They bind the active queue manifest
`58c39d64510f37fda8eaf6912ed36001845f276239dcaeec0ea24ba4a6a2836c`
and keep IDs in queue order. An exclusion means only “do not select this row in
that checkpoint”; it does not mean that a successful change analysis exists.

| Selection | Excluded IDs | Exact meaning | SHA-256 |
| --- | ---: | --- | --- |
| `active-exclusions-v1` | 12 | Five completed v2 qualification rows plus seven historical reviewed algorithm-v1 rows | `8f6155b9720ce78b8536748294f37ed10079fa496a9f08d26f80e89a36446a6f` |
| `active-exclusions-v2` | 22 | Thirteen completed v2 rows, seven historical reviewed v1 rows, and two France edge failures | `08e98a2e11c8181d17cb0d8d8076efafd57616ae595ff1ce4ec9274932c9473a` |
| `active-exclusions-v3` | 44 | Twenty-two completed v2 rows, seven historical reviewed v1 rows, and 15 rows whose originally selected asset pair crosses a required read-window edge | `829d5a0e6c7fa6897423d04cde58e1fdfca62e9ea1d4a04e96658769c56e5bb1` |

The v3 total of 44 is therefore not 44 successful analyses. The 15 edge-blocked
rows comprise 13 rows that lacked a current output plus two clipped historical
review inputs at queue positions 27 and 60. A separate versioned reselection
lane may bind alternate full-cover assets already present in the exact archived
catalog responses; the legacy exclusion files are never rewritten for that
purpose. France positions 14 and 15 have no full-cover baseline feature in the
archived response and remain unresolved pending separately versioned mosaicking
or supplemental-scene evidence.

“Full-cover” means that every selected asset covers the native read window and
required interpolation support. It does not imply a `valid_pixel_fraction` of
one: cloud, shadow, and nodata masks can still reduce valid coverage. No
selection or exclusion creates a data-centre identity, lifecycle, construction,
operator, type, capacity, power, energy, PUE, workload, or unique-site fact.
