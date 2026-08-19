# Catalog-reselection-v2 change runner

`satellite_reselected_change_batch_v2` is a collision-isolated carrier for
running the unchanged Sentinel-2 numerical change processor against a frozen
`satellite_catalog_reselection_v2` release. It does not reinterpret the
original provider batch, edit the atlas, or infer site identity, lifecycle,
operating status, operator, type, IT capacity, PUE, workload, power, energy,
load, or unique-site counts.

The legacy reselection runner, scripts, tests, and documentation remain the v1
contract. This file describes only v2.

## Input contract

Every invocation supplies:

- one immutable review queue;
- the original catalog batch used by the v2 reselection plan;
- one or more explicit `--queue-id` values; and
- the already-built, frozen v2 reselection release.

The runner calls `validate_catalog_reselection_v2` with those exact inputs.
Repeated or reversed explicit IDs are reproduced through the v2 planner, which
deduplicates them and orders them by immutable queue position. The runner does
not contain a static supported-ID list.

The release's canonical candidate inventory must be partitioned exactly into
disjoint `supported_queue_ids` and `unresolved_queue_ids`. Only the supported
inventory returned by `release_catalog_tasks_v2` becomes numerical work.
Unresolved candidates remain explicit in the checkpoint and have no task or
processor invocation. A valid all-unresolved release therefore completes with
zero selected jobs rather than inventing work or dropping the unresolved
record.

## Closed-world and resume guarantees

Before execution, between jobs, and after the invocation, the runner checks:

- original queue and catalog lineage;
- exact frozen v2 release file and directory inventories;
- every release artifact byte count and SHA-256;
- release file mode `0444` and directory mode `0555`; and
- the numerical processor, adapter, CLI, catalog-v2 carrier, runtime, and
  dependency lineage captured in the checkpoint.

An extra file, missing file, changed byte, mode drift, symlink, source-manifest
change, processor change, or runtime change fails closed. Each job writes to a
staging directory, is validated twice, fsynced, and atomically renamed before
the checkpoint records completion. The output itself is a closed tree.

`max_jobs`, `max_job_attempts`, `timeout_seconds`, and
`minimum_interval_seconds` bound an invocation. The canonical checkpoint is
written atomically after every state transition. A later invocation resumes
the same selected inventory and configuration; exhausted jobs are not retried.

## Offline validation

From the repository root, this validates queue, original catalog, frozen
release, candidate outcomes, task bindings, processor files, and runtime
without executing change analysis:

```bash
python scripts/run_satellite_reselected_change_batch_v2.py \
  --queue-dir satellite_review_queues/2026-07-20-open-seed-v43 \
  --source-catalog-batch-dir satellite_review_runs/2026-07-20-open-seed-v43-active-001 \
  --queue-id satq-d0a872a7aee9f9f54a8631ef \
  --queue-id satq-cef871428da247c3ecfadec6 \
  --queue-id satq-d0a872a7aee9f9f54a8631ef \
  --reselection-release-dir satellite_catalog_reselection_runs/2026-07-20-open-seed-v43-active-v2-001 \
  --validate-inputs-only
```

The repeated, reversed input above must validate to queue order
`satq-cef871428da247c3ecfadec6`, then
`satq-d0a872a7aee9f9f54a8631ef`.

## Bounded execution and output validation

Execution requires a separate output directory:

```bash
python scripts/run_satellite_reselected_change_batch_v2.py \
  --queue-dir satellite_review_queues/2026-07-20-open-seed-v43 \
  --source-catalog-batch-dir satellite_review_runs/2026-07-20-open-seed-v43-active-001 \
  --queue-id satq-cef871428da247c3ecfadec6 \
  --queue-id satq-d0a872a7aee9f9f54a8631ef \
  --reselection-release-dir satellite_catalog_reselection_runs/2026-07-20-open-seed-v43-active-v2-001 \
  --output-dir satellite_change_runs/example-v2 \
  --max-jobs 1 \
  --max-job-attempts 3 \
  --timeout-seconds 1800 \
  --minimum-interval-seconds 1.1
```

Re-run the same command to resume. To validate an existing output without a
processor invocation, add `--validate-only` and preserve the saved bounds.

The output remains a set of visible-change proposals requiring analyst review.
It is not evidence that a feature is a data centre and is not a claim about
construction, operation, capacity, energy use, or ownership.

## Focused tests

The offline test module covers dynamic IDs, repeated/reversed canonicalization,
lineage, all-unresolved zero-job behavior, mocked atomic processor success,
bounded failure and resume, timeout and interval forwarding, release and output
tamper rejection, v1 byte pins, and both supported import layouts. Its socket
and raster-open guards make unintended network or pixel access fail the test.

```bash
python -m unittest tests.test_satellite_reselected_change_batch_v2 -v
```
