# Resumable satellite catalog batch

`scripts/run_satellite_review_queue.py` processes the verified review queue one job at a time through
the existing `catalog_satellite.py` command. The runner operates in **catalog-only** mode: it saves
bounded STAC responses and selected Sentinel item IDs, but does not download imagery, run change
analysis, edit atlas entities, or infer identity, lifecycle, operating status, or power.

Use an execution directory separate from the closed-world queue bundle:

```sh
python3 scripts/run_satellite_review_queue.py \
  --queue-dir satellite-review-queue \
  --output-dir satellite-review-run \
  --lock-file satellite-review-run.lock \
  --priority-tier active_construction \
  --priority-tier proposed_pipeline \
  --max-jobs 25 \
  --max-http-attempts 50 \
  --max-response-bytes 16777216
```

Omit `--priority-tier` to select all tiers. Selection is pinned in the first batch manifest, so a
resume must use the same tiers and network settings. To run a different selection, use a new output
directory.

`--lock-file` is required and must name the canonical persistent sibling derived from the resolved
output path: `<output-directory>.lock`. For example, `--output-dir satellite-review-run` requires
`--lock-file satellite-review-run.lock`. The canonical file must remain outside both the closed-world
queue and output bundle. The
runner holds a non-blocking exclusive `flock` on its open descriptor for the complete execution.
Contention fails before queue or output mutation, process exit releases the kernel lock, and the
runner never removes the lock file. A different supplied lock path is rejected, so aliases and
caller choice cannot create two lock domains for the same cumulative output.

## Network and budget contract

Every catalog job contains two STAC POSTs: one baseline window and one current window. The batch
runner defaults to no catalog retries and reserves `2 × (retries + 1)` possible HTTP attempts before
starting each job. A job runs only if that entire worst-case reservation fits under
`--max-http-attempts`; actual attempts cannot exceed the cap even when a subprocess
fails. `--max-jobs` applies a separate cap to subprocess invocations.

The runner passes a descriptive `User-Agent` to `catalog_satellite.py`. It enforces the configured
minimum interval inside each catalog command, including retries, and also waits that interval
between sequential catalog processes. Defaults are a 1.1-second minimum interval, a 60-second
request timeout, three batch attempts per job, and zero HTTP retries. Each catalog response is also
streamed under a 16 MiB default cap. `--max-response-bytes` is passed explicitly to every catalog
subprocess and pinned in the schema-v3 batch configuration, so a resume cannot silently change it.
An oversized declared `Content-Length` is rejected before reading; a truncated, conflicting, or
invalid length is rejected; and an absent or underreported length cannot bypass the streaming cap.

## Checkpoints and resume

`batch-manifest.json` hash-checkpoints every completed catalog file, selected item ID, retrieval
timestamp, job attempt, and bounded failure. Catalog commands write to an executor-owned staging
directory. The executor reconstructs and validates each successful directory from its exact baseline
and current response bytes before atomic promotion to `jobs/<queue-id>/catalog`.

On every resume, the runner first revalidates:

- the queue's exact closed-world file set, sidecar, canonical manifest and JSONL, hashes, counts,
  ordering, and deterministic job templates;
- the batch manifest's queue lineage, configuration, task inventory, review-only scope, and summary;
- all completed catalog directories, including their exact three-file set, canonical manifest,
  response hashes, query bounds, selected IDs, labels, and scope note.

Any changed or missing completed artifact stops the run before another network request. Genuine
command, transport, response, and output-validation errors retain a failed state and may be
retried on a later bounded run until `--max-job-attempts` is reached.

`validate_satellite_batch(queue, run, config=...)` performs the same queue, checkpoint, and terminal
artifact reconstruction offline without changing the completed manifest or making a network call.

The one terminal non-error outcome is `unavailable_no_scene`. The runner records it only when the
catalog subprocess ends with the exact typed `CatalogValidationError` saying that no scene falls
within the pinned baseline or current temporal window. Its checkpoint preserves the raw reason,
which window was unavailable, and that window's exact provider, bounding box, start, end, target,
and day limit. It produces no catalog artifacts or imagery claim, does not widen the query window,
is counted separately from failures, and is skipped on every resume. Similar-looking text, a
different catalog validation error, or any untyped failure remains a retryable failure.

Schema-v2 checkpoints remain offline-validatable without a rewrite. Executing a copied schema-v2
checkpoint with the default cap first validates its exact legacy configuration and every terminal
artifact, reproduces every completed catalog, and verifies the actual baseline/current response
sizes are at most 16 MiB. Only then is the checkpoint atomically upgraded to schema v3. The
migration record explicitly says historical acquisition was not bounded, records the historical
terminal/completed/response counts and largest saved response, and makes the cap effective only for
subsequent attempts. A non-default cap is not silently retrofitted onto schema v2; use a new batch
when a different cap is required.

Schema-v1 checkpoints use the same terminal-artifact and response-size audit while preserving their
typed no-scene migration. They are upgraded only after their complete legacy structure, lineage,
configuration, scope, task inventory, counters, and canonical encoding validate. Existing failed
tasks are reclassified only when their final stored failure contains the same exact typed no-scene
condition; all other failures retain their original state and attempt history.

## Change analysis remains a separate reviewed step

This catalog runner does not execute `sentinel_change.py`. The separate
[resumable change-analysis batch](satellite_change_batch.md) consumes only its validated completed
catalog tasks, resolves the pinned baseline/current IDs and queue arguments, and publishes bounded
visible-change proposals for review. It preserves the queue's no-inference constraints and never
treats imagery as automatic proof of a data-centre identity, lifecycle state, operating status,
type, capacity, power, or energy. Change-batch counts are not additional catalog jobs or accepted
analyst decisions.

## 2026-07-18 priority run

The `global-open-v3` queue manifest is pinned by SHA-256
`58c39d64510f37fda8eaf6912ed36001845f276239dcaeec0ea24ba4a6a2836c`. Separate directories hold
the two highest-priority tiers, and both passed offline validation:

| Tier | Selected entity rows | Scene pairs | No-scene outcomes | Failed | Batch manifest SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| Active construction | 74 | 65 | 9 | 0 | `ff0323728733557727b8d07c9aae6e2801be8a430b0b5e4f4fe7d2a168079a5a` |
| Proposed pipeline | 20 | 16 | 4 | 0 | `e012b06344c2332e1e3192f005db099f15058b973505e7be09907e2ff221e2f6` |

These are atlas entity rows, not deduplicated sites. The catalog pass selected 81 reproducible
before/after pairs across 94 rows and recorded 13 bounded windows with no qualifying scene; it did
not run computer vision or change atlas claims.

### Current cumulative unknown checkpoint

The accepted frozen
`satellite_review_runs/2026-07-21-global-open-v3-unknown-034/` checkpoint continues from the
independently accepted Unknown033 recovery, not from the provenance-contaminated Unknown031
checkpoint. The source recovery was validated offline before an APFS copy-on-write clone was made;
the clone consumed only 7,852 KiB of observed available space before execution despite its 2.9 GB
logical source tree. One bounded pass processed positions 4,770 through 4,794 with 25 first attempts
and 50 reserved HTTP attempts. It produced 22 reproducible scene pairs, three typed baseline-window
no-scene outcomes, and zero failures.

Unknown034 now records 4,397 scene pairs, 303 no-scene outcomes, zero failures, and 2,036 pending
unknown-tier jobs; position 4,795 is next. Its batch-manifest SHA-256 is
`9cc51440c6d0f53a20f45fef61cf33345a47d0dd2f22265b188a692bd3eb6ebd`. The frozen tree contains
13,437 files in 9,134 directories and 3,108,654,345 logical bytes; its canonical inventory SHA-256
is `063dae0d7be8b831e8f4eaedba9d71d2fa2c051640c03a41e2d639144cb5cb3b`. The separate continuation
acceptance manifest is pinned at
`7ec2eff11515b7ffe18ea581e6c73fdf3751902d8bcb7e4fb94ffd380707c74a`.

Active-001, proposed-001, and Unknown034 form the current non-overlapping catalog accounting:
6,830 queue jobs, 4,478 completed pairs, 316 no-scene outcomes, zero failures, and 2,036 pending.
Unknown034 replaces every earlier cumulative unknown checkpoint in current totals. It remains a
catalog-only, review-required checkpoint: no imagery was downloaded, no change analysis ran, and no
identity, lifecycle, operating-status, capacity, power, completeness, or parity claim was created.

### Historical Unknown030 checkpoint

The frozen
`satellite_review_runs/2026-07-18-global-open-v3-unknown-030/` checkpoint covers all 6,736
unknown-lifecycle jobs. It records 4,350 scene pairs, 300 no-scene outcomes, zero failures, and 2,086
pending jobs. The manifest state is intentionally `incomplete`: this is a bounded catalog-only
checkpoint, not a completed global queue. The final bounded pass reserved 500 HTTP attempts for 250
jobs and produced 217 pairs plus 33 typed baseline-window no-scene outcomes. Its batch-manifest
SHA-256 is `18d154cfa6a445be775d6e7c35aea4d9c89d6fd84d57054ef00e541a5f56d053`.
The independently reproduced checkpoint contains 13,296 files in 9,037 directories, totaling
3,075,610,237 bytes; its canonical `path\0size\0sha256\n` inventory SHA-256 is
`e18888591da21236ab62c5dce06cb5f9c6e9deaee399b5740874e8fb6f813432`. During the independent
audit, a concurrent external process applied the permission-only `0555`/`0444` seal. Complete
pre/post content hashes were unchanged, and socket-disabled validation passed again.

Unknown030 preserves Unknown029's sealed catalog checkpoint and all 35 historical `change/`
directories (245 files). Those carry-forward files are byte-identical to Unknown029 and remain outside the
catalog-only batch manifest; they do not mean this pass ran computer vision or change analysis.
The pass mutated no atlas claim and inferred no identity, lifecycle, operating status, or power.
Only global priority positions 4,495 through 4,744 changed; the next position is 4,745. Within the
unknown tier those positions are 4,401 through 4,650, with 4,651 next. Active-001, proposed-001, and
unknown-030 formed the then-current non-overlapping catalog accounting: 6,830 queue jobs, 4,431 completed
pairs, 313 no-scene outcomes, zero failures, and 2,086 pending. The unknown-030 count replaces
unknown-001 through unknown-029; current totals must not add any older
cumulative checkpoint.

Candidate-fusion v13 remains frozen at the earlier Unknown015 catalog state and 43 historical
algorithm-v1 analyst report/review pairs, including 12 retained follow-ups and 31 rejected masks.
Six pairs are the Unknown013 additions and six are the Unknown015 additions. Queue
availability and retained visual change remain review signals, not identity or lifecycle evidence.

The six Unknown013 comparisons also act as bounded controls. Meta Los Lunas had 100% mutually valid pixels
and Google Thornton had 99.97%; visual review retained both for manual follow-up because the changed
large-roof surfaces were site-aligned. Microsoft Data Center 2 (14.27% mutually valid), Amazon
IAD131 (30.52%), Iceland M05 (50.42%), and Vantage WA12 (100%) were rejected: the first two had weak
or obscured common coverage, the Iceland changes were off-site, and the Vantage mask was dominated
by agricultural, road, reservoir, and surface changes. None of the six decisions creates or changes
an atlas identity, lifecycle, capacity, power, energy, type, workload, or operating-status claim.

The six Unknown015 comparisons add two retained follow-ups and four rejection controls. Meta Eagle
Mountain had 99.99% mutually valid pixels and visibly added multiple large campus buildings; QTS
NAL 2 DC2 had 94.10% and showed a new large building east-southeast of the established campus.
Microsoft Iowa and CyrusOne PHX7 had clear pairs but no unambiguous new site footprint. Amazon
IAD125 had only 59.57% mutually valid coverage, and the Argentine OSM control had 17.12% with no
filtered component. All six decisions remain manual-review labels and create no atlas fact.

### Historical cumulative checkpoints

The separate 6,736-row unknown-lifecycle tier first ran in
`satellite_review_runs/2026-07-18-global-open-v3-unknown-001/`. Its two bounded passes reserved
300 HTTP attempts and processed 150 rows: 146 reproducible catalog pairs, four no-scene
outcomes, and zero failures. Candidate-fusion v4 pins this frozen checkpoint's
exact manifest. Its SHA-256 remains
`68129af4d5f6c89ee25240b2ee299a77fa40f2960f0fa5fb6c1a0a369b15459b`.

Work continued from a validated byte-identical copy at
`satellite_review_runs/2026-07-18-global-open-v3-unknown-002/`. One bounded pass reserved
200 HTTP attempts and processed 100 more rows: 96 reproducible pairs, four no-scene
outcomes, and zero failures. The frozen continuation records 242 pairs, eight no-scene
outcomes, zero failures, and 6,486 pending jobs. It remains `incomplete`, performs no
change analysis or status promotion, and revalidates offline. Its manifest SHA-256 is
`88f20ed878740d09e710fb8f90c1f79177423433c2951d9aec1f247d59b2b732`.

Do not resume a pinned directory after a downstream bundle references it. Continue from a new
validated copy to preserve byte reconstruction for prior fusion and coverage artifacts.

Analysts chose two clear pairs for pipeline QA. The EAT12 development
project pilot had 92.85% of pixels valid in both images and proposed seven components totaling 153,100 m².
Visual review retained it only as a site-aligned change candidate: a new large-roof complex is
visible in the AOI, but neither its identity nor lifecycle was inferred from imagery. The report
SHA-256 is `56a05e89e23f4a646a886a90ae62cbd39dd8ad8c925c68bc4f3e4733c3a78089`; the separate analyst
decision is `7b2224d610905dd82712cc90c0130bce834026208639d3740cafeba47842d803`.

The proposed QTS Hillsboro 3 pilot had 99.98% valid pixels but proposed 24 components totaling
794,200 m². Visual review found the mask dominated by agricultural-field and off-site surface
changes, so it was rejected for site promotion. Its report SHA-256 is
`c883b60695d3ac37a310f4255e52c01f36b604f7a4e34ff31d5d90b65089fbe6`; the rejection decision is
`6364d6161e094f02c50e91d40d4af25485e63c59d1ad1ffe0ae617c5860a4bca`. This negative control is
retained because low cloud cover and a large change area are not sufficient evidence of data-centre
construction.

Analysts processed two clear pairs from the unknown-lifecycle run. The Microsoft EAT03
PNNL/IM3 container AOI proposed 25 components totaling 454,100 m². Manual comparison found several
new large-roof industrial buildings inside the campus AOI and retained only a site-aligned visual
change candidate. PNNL/IM3 is OSM-derived, and no independent evidence confirmed the identity or
lifecycle. Its report SHA-256 is
`27868ccfff1c3ab9004692d49b9b1eb759aabba00c79b921c1ba08144a1b99d4`; the review decision is
`eedde143563b4de2ef67ca743d892fa4aac3c67a366f8e2dfbddf76e02b94960`.

The OpenStreetMap way 775412067 AOI proposed eight components totaling 172,400 m², but the clearest
large-roof and earthwork changes were away from the entity point. It was rejected for site
promotion and creates no lifecycle claim. Its report SHA-256 is
`cd8c93dac87b952aee7d6179a84c62a2d2840e419e1c7e4411b2980394884226`; the rejection decision is
`83860b98638e8434edbabc9560ac117e1592b53999b8614be0eadcba9d74e90e`.

Analysts reviewed two matched-date, low-cloud pairs from the frozen continuation. The AWS
us-west-2 PNNL/IM3 container AOI had 99.92% of pixels valid in both images and proposed 25 components
totaling 1,320,300 m². Manual comparison found multiple new large-roof buildings within the bounded
campus AOI, but many mask polygons also covered agricultural fields, ponds, and surface changes.
Only a site-aligned visual-change candidate was retained; PNNL/IM3 remains OSM-derived, and no
identity, lifecycle, or power claim was created. Its report SHA-256 is
`062fe4d08d08912b3707658b4d82de02393ec6275b63da57066868404e82b745`; the review decision is
`5404ed547c50a62648cfdfa80106c9aa7a2207893fd5b1d46d975a9a0550a535`.

The Spanish OpenStreetMap way 1505120011 AOI had all pixels valid in both images and proposed 14
components totaling 310,500 m². The central industrial area showed little change, while the mask was
dispersed across fields, roads, roofs, and unrelated urban surfaces. It was rejected for site
promotion and creates no identity or lifecycle claim. Its report SHA-256 is
`8c9096bc524d952444e3d9803e1ed545587825e8ce8093533510c0882794f58a`; the rejection decision is
`60d22e31fa437a35ded2232d255ed412a029f22a111509416a586c8b72a0de09`.
