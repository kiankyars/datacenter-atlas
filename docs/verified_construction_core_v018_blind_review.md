# v0.18 blind-review gate (contract schema v3)

The authoritative contract is the module docstring of
`datacenter_atlas/verified_construction_core_v018.py`; this note is a short guide for the people and
agents who write the results record and build the first v3 checkpoint.

## What v3 adds

Schema `datacenter-atlas-v018-reviewed-batch-v3` is schema v2 plus one required key, `blind_review`,
which pins two committed files by path, byte count and SHA-256: the pre-registration under
`definitions/` and the results record under `sources/`. In v3, `baseline_corrections` may be empty.
`ReviewPins` gains `blind_review_sha256`, the `canonical_sha256` of that entry; it is required for v3
and must be `None` for v1 and v2, which reject a `blind_review` key. v1 and v2 checkpoints, their
formats and their bytes are unchanged.

v3 also accepts one optional key, `baseline_withdrawals` (see the last section). A v3 contract
without it builds exactly the bytes it built before withdrawals existed.

The pre-registration must be the one registered in builder code (`BLIND_REVIEW_PREREGISTRATIONS`,
keyed by the population release's manifest SHA-256). A contract therefore cannot pin a second sample
of the same population or a sample drawn from a chosen seed; a new population needs a new published
pre-registration and a reviewed change to that constant. The builder also recomputes the
pre-registration from scratch before reading any result: the population release's sorted project
keys and their hash, the seed material (`datacenter-atlas-blind-review-v1|<keys sha256>|<commit>`),
the seed hash, the 20 smallest `sha256(seed_sha256 + "|" + key)` ranks in order, and every blind
input. The published pre-registration
(`definitions/verified-construction-core-v0.18-blind-review-preregistration-v1.json`) recomputes
exactly against the thirty-sixth checkpoint's 203 projects, and a unit test pins that.

## Writing the results record

The record schema is `datacenter-atlas-v018-blind-review-results-v1`; its fields and rules are listed
in the module docstring. Four points need care.

- **Location rows are compared with the reviewed rows.** Each location rule is computed from the
  reviewer point and the site geometry in the *pre-registered population release* (the thirty-sixth
  checkpoint), never from the checkpoint being built. Compute each row with the builder's own method,
  so that the recorded distance and rule match the recomputation:

  ```python
  from datacenter_atlas.verified_construction_core_v018 import blind_review_location_comparison

  result = blind_review_location_comparison([longitude, latitude], site_geometry)
  # result["band"] is inside, within_1000m, adjudication_band or beyond_3000m.
  ```

  The site geometry is the `geometry_json` of the project's site row in that release. Use the
  geometry, not the display anchor: three frozen v0.17 polygon anchors (Borealis Blönduós, Racks
  Central Johor and Microsoft Mount Pleasant) lie 3 to 30 m outside their own polygons. Record the
  distance with enough precision that it agrees within max(5 m, 1 %) and lies in the same band as the
  rule: exactly 0 for `inside`, at most 1,000 m for `within_1000m`, more than 1,000 m and at most
  3,000 m for an adjudicated rule, and more than 3,000 m for `beyond_3000m`.
- **Adjudication is attributable.** In the 1,000–3,000 m band a row needs `adjudication:
  {adjudicated_by, adjudicated_at, reason}`. The adjudicator is not a reviewer session, and the date
  falls between the latest counted review and `recorded_at`; elsewhere `adjudication` is `null`.
- **The counted session is fixed by rule, not chosen.** Every session carries `session_sequence`
  (its start order, a unique positive integer, for example the orchestration journal line that
  started it) and
  `session_status` (`completed` or `aborted`). At each position the counted session is the completed
  *blind* session with the lowest sequence. A session is blind when it attests no Atlas access and
  none of its evidence or location URLs is an Atlas surface: the site, the repository or any fork
  of it, its raw, codeload, API or jsDelivr mirrors, or an archived copy of any of these. Every other
  session is recorded uncounted, with `counted_session_id` and the matching `uncounted_reason`:
  `aborted` (an interrupted attempt with no output, carrying only `abort_notes`),
  `blindness_breach`, or `later_duplicate`. The draft reports every uncounted session with its
  determination, and it reports the record's `disclosures`. The disclosures must state that the
  reviewers were AI agents. The rule is builder code, not part of the pre-registration (which says
  only "one session per sampled project"). In round44 it was written after the sessions and the
  comparison had run; it was outcome-neutral there, and the record discloses its timing.
- **Reviewer outputs are normalised, and may be kept verbatim.** The record needs
  `successor_check: {status, notes}` and `blindness_attestation: {atlas_materials_accessed,
  statement}` objects, and its evidence and location items accept only the listed keys. A
  reviewer's own output can be kept as `reviewer_output` on its session. When that output carries an
  integer position, a canonical determination or a numeric point, these must equal the recorded
  values.

Draft outputs report the record's pinned distances, never the recomputed floats, because platform
trigonometry can differ in the last bits and the drafts must rebuild byte for byte on any machine.

## The gate

A checkpoint is the pre-registered population only if two things hold. It has exactly the reviewed
release's sorted project keys, and every project keeps its blind-reviewed claims:

- on the project row: site key, name, country, geometry, status and status date;
- on the site row: name, country and geometry.

Imagery outcomes, evidence and geometry semantics are not blind-reviewed, so changing them keeps the
population.

When the checkpoint is that population, the `blind_review` gate reports `sample_size`, `agreements`
and `passed` (at least 19 of 20). It also reports both file pins, the seed, the per-position outcomes
with any adjudication, every uncounted session, the counted-session rule and the disclosures.

Otherwise, the gate still reports the same result, with `passed: false` and `population_mismatch`
details. Those details list the projects whose claims changed and the sampled positions that are no
longer covered. This happens, for example, when projects are added or dropped, or when a reviewed
name, status or geometry is edited. A disagreement therefore cannot be fixed in its row and
re-scored, and a new pre-registered sample is needed. Every other gate, and
`publishable_as_final: false`, is unchanged.

A v3 checkpoint needs its own batch module whose `ReviewPins` set `blind_review_sha256`, an entry in
`scripts/build_expansion_200_draft.py`, and CI steps for the new checkpoint and for
`tests/test_verified_construction_core_v018_blind_review.py`.

## Baseline withdrawals

A versioned review can find that an inherited v0.17 project's selected evidence does not meet the
acceptance contract (round44: SBOGZB01, sampled at position 10). A v3 contract can then remove it
with a pinned `baseline_withdrawals` entry. Its record (schema
`datacenter-atlas-v018-baseline-withdrawal-v1`, a committed `sources/` file) names the frozen rows by
line number, row hash and raw-line hash, and binds the withdrawn status observation to its frozen
curated v0.17 input. It pins the versioned review as its `review_basis` and states the
checkpoint-independent count effect. The module docstring lists every field and rule.

- **What is removed.** A withdrawal removes the project row, its single-project site row and GeoJSON
  feature, and the evidence rows only that project used. Every other inherited byte keeps its order.
  Counts, country counts and every gate are recomputed. A project on a shared site, or with a shared
  evidence row, is rejected, because it would need a reviewed re-derivation of those rows.
- **What is never claimed.** A withdrawal asserts no physical status. Its record must carry the exact
  `claim_boundary`: no asserted status, status on 2026-08-20 `unknown`, and not paused, cancelled,
  completed or not under construction. The draft therefore asserts no status for the project: its
  project row is gone, and the selection report keeps the withdrawn observation only as
  non-qualifying audit context (`withdrawn_selected_observation`, with `qualifies_for_selection:
  false`), as the round44 versioned review asks.
- **What is left as it is.** A withdrawal neither changes nor re-reviews any other row. Its record
  must list, exactly, every other frozen evidence row that shares a withdrawn row's source capture
  (the same source URL and content hash), in `shared_capture_rows` with a statement of how the
  review treated them. The `withdrawal_shared_capture_review` final-release gate lists the selected
  projects that still rest on such a capture and passes only when none remains. For SBOGZB01 these
  are SSCLHB01, SSCLLP01 and SFORPF01: their status rows come from the same 2026-07-21 Scala
  portfolio capture, and the versioned review did not evaluate them, so each needs its own versioned
  review before a final release. `ATTRIBUTION.txt` keeps every inherited v0.17 notice, including
  notices for sources that only the withdrawn rows used.
- **Corrections.** A project cannot be both corrected and withdrawn. For SBOGZB01, the withdrawal
  supersedes the host-zone locator rescope.
- **The gate.** A withdrawn project is absent from the checkpoint, so a pre-registered population
  that contains it never matches, and `passed` is false. A withdrawn sampled project is reported,
  not re-scored: `population_mismatch` also lists `reviewed_projects_withdrawn` and
  `sampled_projects_withdrawn` (position, key and withdrawal ID), and the README names the position.
  A new pre-registered sample of the post-withdrawal population is needed before the gate can pass.

Inherited-through checks locate frozen lines and the frozen feature by their bytes, not by line
number or feature index. A withdrawal shifts later lines and features, so a later correction can
still name a draft with a withdrawal as its inherited-through release.

## Round44 versioned reviews

The two round44 disagreements each triggered a versioned, non-blind review of its row, kept as a
committed `sources/` file and named, with its SHA-256, in disclosure text of the results record:

- Position 10, SBOGZB01:
  `sources/research-expansion-200-sbogzb01-status-disagreement-round44-2026-10-09.json` (68,442
  bytes, SHA-256 `7807da44…01ba`). It finds that the selected status does not meet the contract and
  recommends withdrawal without any paused or cancelled claim; it is the review basis pinned by the
  SBOGZB01 withdrawal record.
- Position 17, ODATA DC SP04 Phase 2:
  `sources/research-expansion-200-round44-blind-disagreement-odata-sp04-phase2-2026-10-10.json`
  (58,908 bytes, SHA-256 `4e368157…19ea`). It keeps the row unchanged. Its added corroboration is
  context only, and its provenance disclosures (the robots-disallowed LinkedIn capture of the
  status evidence and the unretained 2026-09-07 geometry bytes) live in the review itself, because
  no mechanism adds evidence rows to a frozen baseline project.

Neither review changes the blind result: 18 of 20 agreements, gate not passed.
