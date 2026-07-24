# Explicit-v1 change disposition

The original explicit catalog execution checkpoint remains untouched and
mutable. Its exact validated bytes are finalized at the separately versioned
`satellite_review_runs/2026-07-21-open-seed-v71-active-explicit-final-v1`
path, frozen at file mode `0444` and directory mode `0555`.

The external disposition under `satellite_change_run_dispositions/` binds the
frozen 11-job change run to that immutable catalog copy. It also records a
post-freeze adapter incident: canonical JSON sorted the `jobs` object keys,
while the adapter incorrectly treated object iteration order as receipt order.
The disposition does not relax selection. It requires the exact ordered
`selection.selected_queue_ids` receipt field, the exact unordered job-key set,
and the same queue-position order.

The accepted artifact is an unreviewed machine change-proposal batch. It
creates no analyst decision and no Atlas identity, construction status,
lifecycle, operator, type, capacity, PUE, workload, power, or energy claim.
