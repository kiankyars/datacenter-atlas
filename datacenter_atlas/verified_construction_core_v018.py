"""Opt-in, additive v0.18 DRAFT builder. The public CLI remains on v0.17.

Two phases are intentionally separate:

1. ``validate_batch(contract_path, review_pins, root=ROOT)`` checks independently
   reviewed input pins, exact source facts, the fixed lifecycle cutoff, geometry
   semantics, distinct-campus review, any pinned baseline correction and, for
   schema v3, the pinned pre-registered blind review and any pinned baseline
   withdrawal. It returns a validated batch without writing anything or
   declaring the 200-site objective complete.
2. ``build_draft(contract_path, review_pins, output_dir, root=ROOT)`` derives all
   rows and denominators, validates a staged reconstruction, then publishes a
   new local draft directory. ``validate_draft`` reconstructs every output byte.
   Under schema v1 all inherited CSV bytes and GeoJSON features remain
   unchanged. Under schema v2 every inherited byte also remains unchanged except
   the exactly enumerated fields of rows named by a pinned baseline correction,
   its dropped superseded evidence rows and the project association it adds to
   shared evidence rows (below). Under schema v3 a pinned baseline withdrawal
   also removes whole inherited lines: its project row, its single-project site
   row and GeoJSON feature, and the evidence rows only it used. No default
   artifact, public CLI, baseline file, or researched candidate is modified.

Contract schema ``datacenter-atlas-v018-reviewed-batch-v1`` (all keys shown are
required; unrecognized keys at these levels are rejected):

    {
      "schema_version": "datacenter-atlas-v018-reviewed-batch-v1",
      "batch_id": "a-reviewed-batch-name",
      "base_preview_manifest_sha256": BASELINE_MANIFEST_SHA256,
      "lifecycle_reference_date": "2026-08-20",
      "geometry_identity_reviewed_at": "YYYY-MM-DD",
      "sources": [{
        "source_id": "status-source",
        "path": "sources/a-curated-file.json",
        "bytes": 1234, "sha256": "64 lower-case hex characters",
        "evidence_pointer": "/evidence/0", "evidence_sha256": "..."
      }],
      "acceptances": [{
        "project_stable_key": "curated:example:phase-1",
        "parent_campus_stable_key": "curated:example",
        "country_iso_a2": "US",
        "identity": {
          "source_id": "status-source",
          "project_pointer": "/project", "project_sha256": "...",
          "campus_pointer": "/campus", "campus_sha256": "..."
        },
        "status": {
          "source_id": "status-source", "record_pointer": "/lifecycle/0",
          "record_sha256": "..."
        },
        "geometry": {
          "source_id": "geometry-source", "record_pointer": "/results/0",
          "record_sha256": "..."
        },
        "distinctness_review": {
          "decision": "distinct_physical_site",
          "scope": "single_physical_site",
          "equivalent_campus_keys": ["curated:example"],
          "baseline_site_keys_sha256": "...",
          "batch_site_keys_sha256": "...",
          "evidence_source_ids": ["status-source", "geometry-source"],
          "reason": "Source-grounded physical-site and alias adjudication."
        }
      }]
    }

Contract schema ``datacenter-atlas-v018-reviewed-batch-v2`` is v1 plus exactly
one more required key, a nonempty ``baseline_corrections`` array. A v1 contract
that carries the key is rejected, and every v1 draft stays byte-for-byte
reproducible. Each correction re-scopes the locator semantics of one inherited
v0.17 project on a single-project site:

    "baseline_corrections": [{
      "correction_id": "a-correction-name",
      "physical_site_stable_key": "frozen v0.17 site key",
      "project_stable_key": "frozen v0.17 project key",
      "frozen_rows": {
        "release_path": BASELINE_RELATIVE_DIR,
        "manifest_sha256": BASELINE_MANIFEST_SHA256,
        "projects_csv": {"file_line_number": 37, "project_stable_key": "...",
                         "row_canonical_sha256": "...", "raw_line_sha256": "..."},
        "sites_csv": {"file_line_number": 36, "physical_site_stable_key": "...",
                      "row_canonical_sha256": "...", "raw_line_sha256": "..."},
        "evidence_csv": {"file_line_number": 136, "evidence_id": "...",
                         "row_canonical_sha256": "...", "raw_line_sha256": "..."},
        "sites_geojson": {"feature_index": 34, "feature_canonical_sha256": "..."}
      },
      "geometry": {
        "source_id": "correction-source", "record_pointer": "/results/0",
        "record_sha256": "..."
      },
      "identity_source_id": "unchanged-frozen-identity-binding",
      "evidence_source_ids": ["correction-source", "other-geometry-source"],
      "reason": "Why the inherited locator semantics are corrected."
    }]

File line numbers count the CSV header as line 1; raw-line hashes cover the
line bytes without the newline. ``evidence_source_ids`` must equal the
correction record's ``geometry_source_ids``; those sources receive only the
``geometry`` role. The geometry source's document is the pinned correction
record. Besides ``evidence`` and ``results`` it carries ``source_bindings``,
``supersedes``, ``required_unchanged_identity_bindings``, ``exact_row_deltas``
(projects.csv, sites.csv, sites.geojson, evidence.csv and one
``counts_relative_to_*`` block) and ``preservation_invariants``, and states
``lifecycle_reference_date`` 2026-08-20, ``accepted_additional_sites`` 0 and a
``reviewed_at`` date between the cutoff and the contract's review date.

A frozen site that binds several geometry captures (an OSM multi-way union) is
corrected as a whole: ``frozen_rows`` may add ``additional_evidence_csv`` (a
nonempty list of evidence row specs shaped like ``evidence_csv``) and the
record's ``supersedes`` then carries ``additional_superseded_evidence``, one
entry per row in the same order: ``evidence_pointer``,
``evidence_record_sha256``, ``evidence_source_id``, ``evidence_id`` and
``replacement_source_id``. Single-capture corrections carry neither key. Each
correction is validated fail-closed:

- Frozen rows: line numbers, canonical row hashes, raw-line hashes and the
  feature hash must match the files of the pinned v0.17 manifest, and the raw
  lines and feature must still match in the later release named by
  ``supersedes.inherited_unchanged_through``. There each frozen raw line, and
  the frozen feature's canonical hash, must occur exactly once; they are
  located by their bytes, not by line number or feature index, because an
  earlier correction's dropped evidence row shifts later evidence lines and an
  earlier withdrawal shifts later lines and features. That release must be a
  v0.18 draft (manifest format v1 or v2; v3 too under a v3 contract) built on
  the pinned v0.17 manifest, never the frozen baseline itself.
- Supersedes: the superseded facts file must be a pinned v0.17 portable input,
  and its hash-bound evidence and geometry records must reproduce the frozen
  evidence row, geometry, display anchor and locator semantics. Every superseded
  evidence row (primary and additional) must be solely this project's geometry
  evidence, the frozen site must bind exactly those rows, and the superseded
  locator's ``geometry_source_document_ids`` must equal the primary source
  followed by the additional sources.
- Identity: ``identity_source_id`` names an unchanged binding to the frozen v0.17
  curated input whose project, campus, lifecycle row and evidence reproduce the
  frozen status. It is never a contract source; its evidence row is unchanged.
  Its evidence may keep an inherited date-only ``retrieved_at`` only because it
  must then equal the frozen status evidence row field for field.
- Geometry: a dedicated validator accepts location basis
  ``host_estate_locality_context``, entity kind ``host_estate`` and use scope
  ``host_estate_context`` ONLY for baseline corrections, never for acceptances.
  Geometry and display anchor must equal the frozen row exactly; authority is
  unchanged and no numeric uncertainty may be asserted. A frozen polygon anchor
  that lies outside its geometry is kept only when the record declares
  ``display_anchor_outside_geometry`` true; acceptances keep the anchor-inside
  rule.
- Reused capture: the primary correction source must reuse the superseded
  capture's URL, rights, publication value, retrieval value and content hash,
  and each additional superseded row is likewise reused by its own distinct
  replacement source. A reused null ``published_at`` equals a frozen empty
  string (both project to the same empty cell); every other value is compared
  literally. Only such sources may keep an inherited date-only ``retrieved_at``.
- Deltas: corrected rows and feature are derived like acceptance rows and must
  differ from the frozen bytes in exactly the enumerated fields; each
  ``unchanged_includes`` entry must be a column of its table. The superseded
  evidence rows are dropped (``removed`` lists the primary row, then the
  additional rows), the enumerated correction evidence rows are added,
  and evidence already used by acceptances only gains the project association.
  Count effects must equal the enumerated block. Every other byte is unchanged.
- Invariants: every ``preservation_invariants`` key is machine-checked and
  unrecognized keys are rejected. Optional ``osm_way_version_unchanged`` must
  equal the superseded record's OSM way version; optional
  ``intersecting_site_rows_unchanged`` lists other site keys, each of which
  must intersect the corrected geometry and keep its project and site lines
  byte for byte from the inherited-through draft;
  ``additional_superseded_captures_unchanged`` is required exactly when
  additional rows are superseded (per row: ``evidence_id``,
  ``raw_evidence_body_sha256_unchanged``, ``raw_capture_retrieved_at_unchanged``
  and optional ``osm_way_version_unchanged``); ``display_anchor_outside_geometry``
  is required, as true, exactly when the frozen anchor is exterior.

``host_estate_context`` maps to verification posture
``recent_authoritative_physical_observation_plus_host_estate_context_only``. It
is excluded from reviewed-locator and official-boundary counts, counted in
``host_estate_context_projects``, and reported in the selection report's
``baseline_corrections`` and ``locator_exceptions`` blocks; such a display
anchor is not a site position. A baseline correction never adds, removes, moves
or merges a site or project, refreshes a lifecycle observation, or certifies a
locator. v2 drafts use manifest format
``datacenter-atlas-verified-construction-core-v018-draft-v2`` and selection
format ``datacenter-atlas-v018-draft-selection-v2``; v1 formats are unchanged.

Contract schema ``datacenter-atlas-v018-reviewed-batch-v3`` is v2 plus exactly
one more required key, ``blind_review``, and one optional key,
``baseline_withdrawals`` (below). In v3 ``baseline_corrections`` may be an empty
list (every entry is still validated as in v2, and a correction's
inherited-through release may also be a v3 draft). A v1 or v2 contract that
carries ``blind_review`` or ``baseline_withdrawals`` is rejected; v1 and v2
behaviour and bytes, and a v3 contract's without ``baseline_withdrawals``, are
unchanged. The ``blind_review`` entry pins two committed files by exact bytes:

    "blind_review": {
      "preregistration": {"path": "definitions/a-preregistration.json",
                          "bytes": 12141, "sha256": "..."},
      "results": {"path": "sources/a-results-record.json",
                  "bytes": 34567, "sha256": "..."}
    }

The pre-registration (schema
``datacenter-atlas-v018-blind-review-preregistration-v1``) must be exactly the
file that ``BLIND_REVIEW_PREREGISTRATIONS`` registers, by path, bytes and
SHA-256, for its population's manifest SHA-256: a contract can neither register
a second sample of a population nor choose a seed. It is recomputed before any
result is read. Its population must name a v0.18 draft (manifest format
v1, v2 or v3, pinned by ``manifest_sha256``, built on the pinned v0.17
manifest, never the baseline itself) whose pinned projects.csv yields
exactly ``eligible_project_count`` sorted project keys hashing to
``eligible_project_keys_sha256``; its scope must be the full expanded
population; ``seed_material`` must be
``datacenter-atlas-blind-review-v1|<eligible_project_keys_sha256>|<published_in_commit>``
and hash to ``seed_sha256``; and the sample must be exactly the 20 keys with the
smallest ``sha256(seed_sha256 + "|" + key)`` (UTF-8, lower-case hex) as
positions 1..20 in rank order, carrying those rank hashes and blind inputs
equal to the release's project name, site (campus) name and country. The
protocol must keep the 2026-08-20 cutoff, the 2026-05-22..2026-08-20 window and
the four blind inputs. ``published_in_commit`` is checked for form and bound
through the seed; a shallow clean clone cannot verify git history, which is why
the accepted pre-registration is registered in builder code.

The results record (schema ``datacenter-atlas-v018-blind-review-results-v1``, a
committed ``sources/`` file; every key is required unless marked optional, and
unrecognized keys are rejected at every level):

    {
      "schema_version": "datacenter-atlas-v018-blind-review-results-v1",
      "recorded_at": "YYYY-MM-DD",
      "preregistration": {"path": "<contract pin path>", "sha256": "<pin>"},
      "population": {<the pre-registration's population object, verbatim>},
      "reviews": [{
        "position": 1,
        "project_stable_key": "<pre-registered key at that position>",
        "reviewer_session_id": "unique-session-id",
        "session_sequence": 7,  # start order: a positive integer, unique
        "session_status": "completed",
        "reviewed_at": "YYYY-MM-DD",
        "counted": true,
        # only, and always, when counted is false:
        # "uncounted_reason": "later_duplicate", "counted_session_id": "...",
        "construction_determination": "under_construction_in_window",
        "construction_evidence": [{
          "source_url": "https://...", "observation_date": "YYYY-MM-DD",
          "literal_pointer": "quoted text or locator", "capture_sha256": "..."
          # optional nonempty text: title, publisher, note, and retrieved_at
          # (YYYY-MM-DD or an ISO datetime with a timezone)
        }],
        "successor_check": {"status": "none_found_on_or_before_cutoff",
                            "notes": "what was checked"},
        "location": {"status": "located", "longitude": 1.5, "latitude": 2.5,
                     "method": "how the point was derived",
                     "source_url": "https://..."
                     # optional: literal_pointer, capture_sha256, notes
                     },
        "identity_notes": "aliases, operator/legal-entity bridges, conflicts",
        "blindness_attestation": {"atlas_materials_accessed": false,
                                  "statement": "what the session did not use"},
        "reviewer_output": {...}  # optional: the session's verbatim output
      }, {
        "position": 2, "project_stable_key": "...",
        "reviewer_session_id": "an-interrupted-session", "session_sequence": 3,
        "session_status": "aborted", "reviewed_at": "YYYY-MM-DD",
        "counted": false, "uncounted_reason": "aborted",
        "counted_session_id": "...", "abort_notes": "what happened"
      }],
      "comparison": [{
        "position": 1, "project_stable_key": "...",
        "construction_agrees": true, "location_distance_m": 0.0,
        "location_rule": "inside", "adjudication": null,
        # in the 1,000-3,000 m band: {"adjudicated_by": "...",
        #   "adjudicated_at": "YYYY-MM-DD", "reason": "..."}
        "agreement": true
        # optional "notes", e.g. a stage difference that does not disagree
      }],
      "totals": {"sample_size": 20, "agreements": 19, "gate_passed": true},
      "disclosures": ["The reviewers were AI agents ...", "..."]
    }

Record rules, each fail-closed:

- Dates: the pre-registration's ``registered_at`` <= every session's
  ``reviewed_at`` <= ``recorded_at`` <= the contract's
  ``geometry_identity_reviewed_at``. No construction observation follows its
  review, and an evidence ``retrieved_at`` day lies between its observation and
  the review.
- Binding: ``preregistration`` equals the contract's pre-registration path and
  SHA-256, and ``population`` equals the pre-registration's population.
- Sessions: ``position`` is 1..20 and ``project_stable_key`` is the
  pre-registered key there; session IDs and ``session_sequence`` values are
  unique. A completed session is blind when it attests
  ``atlas_materials_accessed`` false and none of its evidence or location URLs
  names an Atlas surface (``ATLAS_SURFACE_URL_PATTERNS``). The counted session
  is not the writer's choice: at each position exactly one session is counted,
  and it must be the blind completed session with the lowest
  ``session_sequence`` there (``BLIND_REVIEW_COUNTED_SESSION_RULE``). Every other
  session names that ``counted_session_id`` and its machine-checked
  ``uncounted_reason``: ``aborted`` (an aborted session, which carries only
  ``abort_notes`` and no reviewer output), ``blindness_breach`` (a completed
  session that is not blind) or ``later_duplicate`` (a later blind completed
  session). An optional ``reviewer_output`` keeps a completed session's verbatim
  output; when it carries an integer position, a canonical determination or a
  numeric point, they must equal the recorded ones.
- Determinations are ``under_construction_in_window`` (needs an evidence row
  observed inside 2026-05-22..2026-08-20 and successor status
  ``none_found_on_or_before_cutoff``), ``not_under_construction_in_window``
  (needs an evidence row) or ``unable_to_verify``. Successor statuses are
  ``none_found_on_or_before_cutoff``, ``found_on_or_before_cutoff`` and
  ``not_checked``.
- Location: ``located`` needs finite WGS84 coordinates, a method and an http(s)
  source URL; ``unable_to_locate`` needs null coordinates and notes, and its
  method and source URL may be null.
- Comparison: one row per position, in order, recomputed from the counted
  review. ``construction_agrees`` is true only for
  ``under_construction_in_window``. The location rule is recomputed from the
  reviewer point and the site geometry of that project's site in the
  PRE-REGISTERED population release, never the checkpoint being built:
  ``inside`` (distance 0), ``within_1000m`` (0 < d <= 1,000 m), the adjudication
  band (1,000 < d <= 3,000 m) or ``beyond_3000m`` (d > 3,000 m); an unlocated
  review compares as ``unable_to_locate`` with a null distance. In the band only
  ``adjudicated_same_campus`` or ``adjudicated_different_campus`` is accepted,
  with an ``adjudication`` whose ``adjudicated_by`` is no reviewer session ID,
  whose ``adjudicated_at`` falls between the latest counted ``reviewed_at`` and
  ``recorded_at``, and whose ``reason`` is nonempty; elsewhere the rule must
  equal the recomputation and ``adjudication`` must be null.
  ``location_distance_m`` must agree with the recomputed distance within
  max(5 m, 1 %) and lie in its rule's band (exactly 0 for ``inside``), but the
  rule is always classified from the recomputed distance. ``agreement`` is
  ``construction_agrees`` and a rule of ``inside``, ``within_1000m`` or
  ``adjudicated_same_campus``.
- Totals: ``sample_size`` 20, ``agreements`` the number of agreements, and
  ``gate_passed`` exactly when ``agreements`` >= 19. ``disclosures`` is a
  nonempty list of unique texts.

Location method (standard library only): a reviewer point covered by a
Polygon or MultiPolygon in longitude/latitude (RFC 7946 straight edges,
boundary inclusive, holes excluded), or equal to a Point, is ``inside`` at
distance 0. Otherwise the distance is the minimum WGS84 ellipsoidal geodesic
distance to the Point or to any ring edge, using Vincenty's inverse formula
(converged to 1e-12 rad; a nearly antipodal pair that does not converge falls
back to the great circle on the mean-radius sphere), minimized along each edge
by golden-section search with both endpoints checked; edges whose
triangle-inequality lower bound cannot beat the best distance are skipped,
which never changes the result. ``blind_review_location_comparison`` exposes
the computation to the comparator.

Gate: v3 drafts use manifest format
``datacenter-atlas-verified-construction-core-v018-draft-v3`` and selection
format ``datacenter-atlas-v018-draft-selection-v3``. A checkpoint is the
pre-registered population only when it has exactly the reviewed release's
sorted eligible project keys and, for every project, the same blind-reviewed
claims: ``BLIND_REVIEW_PROJECT_CLAIM_FIELDS`` of its project row and
``BLIND_REVIEW_SITE_CLAIM_FIELDS`` of its site row (identity, status and
location; imagery outcomes, evidence and semantics are not blind-reviewed).
Then the ``blind_review`` gate reports the recomputed ``sample_size`` and
``agreements``, ``passed`` (at least 19 of 20), both file pins, the seed, the
reviewed population and claim fields, the per-position outcomes with any
adjudication, every uncounted session, the counted-session rule and the
record's disclosures. Otherwise, for example after a later checkpoint adds or
drops projects or edits a reviewed name, status or geometry, it reports the
same inherited result with ``population_mismatch`` details (including the
projects whose claims changed and the sampled positions no longer covered) and
``passed`` false: a different population never passes, and a disagreement
cannot be re-scored by editing its row. ``validate_blind_review_preregistration``
recomputes a pinned pre-registration on its own, without a contract or results
record.

Baseline withdrawals (schema v3 only; when present the list is nonempty) remove
one inherited v0.17 project each from the selection, because its selected
evidence no longer meets the acceptance contract, without asserting any
physical status for it:

    "baseline_withdrawals": [{
      "withdrawal_id": "a-withdrawal-name",
      "physical_site_stable_key": "frozen v0.17 site key",
      "project_stable_key": "frozen v0.17 project key",
      "frozen_rows": {
        "release_path": BASELINE_RELATIVE_DIR,
        "manifest_sha256": BASELINE_MANIFEST_SHA256,
        "projects_csv": {"file_line_number": 91, "project_stable_key": "...",
                         "row_canonical_sha256": "...", "raw_line_sha256": "..."},
        "sites_csv": {"file_line_number": 90, "physical_site_stable_key": "...",
                      "row_canonical_sha256": "...", "raw_line_sha256": "..."},
        "evidence_csv": [{"file_line_number": 29, "evidence_id": "...",
                          "row_canonical_sha256": "...", "raw_line_sha256": "..."}],
        "sites_geojson": {"feature_index": 88, "feature_canonical_sha256": "..."}
      },
      "record": {"path": "sources/a-withdrawal-record.json",
                 "bytes": 5429, "sha256": "..."},
      "reason": "Why the inherited selection is withdrawn."
    }]

The record (schema ``datacenter-atlas-v018-baseline-withdrawal-v1``, a committed
``sources/`` file pinned by exact bytes and never a contract source; exactly
these keys) carries ``schema_version``, ``withdrawal_id``, ``project_stable_key``
and ``physical_site_stable_key`` equal to the entry's; ``reviewed_at`` between the
cutoff and the contract's review date; ``lifecycle_reference_date`` 2026-08-20;
``accepted_additional_sites`` 0; ``decision`` ``withdraw_from_selection``;
``withdrawal_basis`` from ``BASELINE_WITHDRAWAL_BASES``; ``claim_boundary``,
exactly ``BASELINE_WITHDRAWAL_CLAIM_BOUNDARY`` plus a nonempty ``statement`` (no
asserted status; the status on the cutoff is ``unknown``; it does not assert
paused, cancelled, completed or not under construction);
``frozen_baseline_rows`` equal to the entry's ``frozen_rows``;
``inherited_unchanged_through`` as for corrections (a v1, v2 or v3 draft in
which every withdrawn line and the feature still occur exactly once, byte for
byte); ``withdrawn_observation_binding``, one binding shaped like a correction's
unchanged identity binding, to the frozen v0.17 curated input whose project,
campus, lifecycle row and evidence reproduce the frozen status observation that
is withdrawn; ``review_basis``, a nonempty list of ``{path, bytes, sha256}`` pins
of other committed ``sources/`` files (the versioned review); ``count_effect``,
the checkpoint-independent effect over ``WITHDRAWAL_COUNT_KEYS`` (physical
sites and projects -1, evidence minus the withdrawn rows, and the withdrawn
project's non-US, reviewed-locator, host-estate and official-boundary
membership); ``shared_capture_rows``, exactly ``{rows, statement}``, where
``rows`` lists in frozen file order every other frozen evidence row that
shares a withdrawn row's source capture (the same ``source_url`` and
``content_hash``) as ``{evidence_id, project_stable_keys,
withdrawn_evidence_id}`` (an empty list when none does) and ``statement`` is
nonempty text on how the review treated them; and a nonempty
``withdrawal_reason``. Validation is fail-closed:

- Frozen rows: located and hash-checked as for corrections. The project must be
  the only project of its single-project site, and ``evidence_csv`` must list,
  once each in file order, exactly the frozen evidence rows whose project
  association names it, each naming it alone. A project on a shared site or
  with a shared evidence row is rejected: it would need a reviewed
  re-derivation of those rows. No other inherited row may reference the
  withdrawn project, site or evidence IDs, and the feature must reproduce the
  site row.
- A withdrawn project or site can be neither corrected nor named as a
  correction's ``intersecting_site_rows_unchanged`` site, and each withdrawal
  targets a distinct project. ``ReviewPins.baseline_withdrawal_sha256`` holds
  exactly one pin per withdrawal_id.
- Output: the project line, site line, evidence lines and feature are dropped,
  every other inherited byte keeps its order, and the builder checks that no
  remaining row names a withdrawn ID and that every remaining evidence row is
  used by a remaining project. Counts, country counts and every gate are
  recomputed from the remaining rows. The selection report's
  ``baseline_withdrawals`` block lists each withdrawal (keys, IDs, record pin,
  basis, claim boundary, the withdrawn selected observation, removed rows,
  review basis, count effect, shared-capture rows, reason), the combined count
  effect (including ``countries`` lost) and the countries left without a
  selected site; the schema's ``v018_draft_contract`` lists the withdrawal
  vocabulary and IDs; the README and provenance disclose them. ATTRIBUTION.txt
  keeps every inherited v0.17 notice.
- Shared captures: a withdrawal neither changes nor re-reviews any other row.
  The ``withdrawal_shared_capture_review`` final-release gate (present only
  with withdrawals) lists every selected project of this checkpoint with an
  evidence row that shares a withdrawn row's source capture, and passes only
  when there is none.
- Blind review: a withdrawn project is absent from the checkpoint, so a
  withdrawn reviewed project always yields ``population_mismatch`` and
  ``passed`` false; the mismatch then also lists ``reviewed_projects_withdrawn``
  and ``sampled_projects_withdrawn`` (position, key, withdrawal_id). A
  withdrawn sampled project is reported, never re-scored.

``ReviewPins(contract_sha256, source_sha256, acceptance_sha256,
baseline_correction_sha256={}, blind_review_sha256=None,
baseline_withdrawal_sha256={})`` is supplied separately by reviewed code, not
loaded from this contract. Its maps bind every source-spec row by source_id,
every acceptance row by project_stable_key, every baseline correction by
correction_id and every baseline withdrawal by withdrawal_id; the optional
correction map defaults to empty and must be empty for v1, and the withdrawal
map must be empty unless the v3 contract carries ``baseline_withdrawals``.
``blind_review_sha256`` is the ``canonical_sha256`` of the v3 ``blind_review``
entry; it is required for v3 and must be None or empty for v1 and v2. All
record/row hashes use ``canonical_sha256``: sorted compact UTF-8 JSON plus one
newline. File hashes use exact bytes. Campus-key-set hashes use sorted lists through
``canonical_sha256``. Review pins must never be automatically refreshed to make
a validation error disappear.

Source evidence objects use the existing curated shape: key, kind, title,
source_url, publisher, source_family, license, attribution, published_at (ISO date,
ISO datetime, or null), retrieved_at, content_hash; extra source metadata is
hash-preserved without normalizing a source publication timestamp.
Identity pointers select literal project/campus objects with stable_key, name,
country. Status selects a literal project lifecycle row with value, as_of_date,
method, evidence_key. Evidence IDs are derived from curated key/content_hash.

A geometry record has exactly project_stable_key, parent_campus_stable_key,
geometry, display_anchor, geometry_source_ids, identity_source_ids,
location_basis, and semantics. Geometry supports Point, Polygon, MultiPolygon.
The anchor is a Point; it must equal a Point geometry or lie within a polygon
(the only exception is a declared frozen anchor kept by a baseline correction).
Semantics has exactly geometry_source_entity_kind, geometry_derivation,
geometry_method, geometry_scope_class, geometry_authority_class,
geometry_use_scope, precision_scope, horizontal_uncertainty_metres, and
horizontal_uncertainty_unknown_reason. ``LOCATION_BASES`` and ``USE_SCOPES``
document the allowed evidence/semantic classes. Locality centroids are excluded,
and the ``BASELINE_CORRECTION_*`` host-estate classes are never accepted here.

Every acceptance is one project on one NEW physical campus. Additional projects
on an already represented site require a different, explicitly reviewed update
workflow, not this expansion path. Alias sets must not collide with the baseline
or another acceptance. Exact coincident anchors fail closed. Geographic alias
review is still a human/source judgment: hashes cannot establish physical truth.
Shared evidence within the delta is supported; baseline evidence IDs may not be
reused because their inherited usage rows must remain byte-for-byte unchanged.
Only a pinned baseline correction may drop an inherited evidence row (only the
superseded geometry rows it names), and only a pinned v3 baseline withdrawal
may drop an inherited project, site, feature or evidence row (only the rows of
the project it withdraws).

Draft output is CSV/GeoJSON plus provenance/report/schema/attribution and manifest.
No public map is generated. Target-count achievement and final-publication
eligibility are separate: this builder ALWAYS labels its output draft and
publishable_as_final=false, including at 200 or more sites. Imagery and blind
review gates are derived from retained rows/review records, never from a constant
success claim. No roles, workload, capacity, efficiency, or energy are inferred.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
import csv
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from types import MappingProxyType
from typing import Any
from urllib.parse import unquote, urlsplit

from . import verified_construction_core_v017 as v17


core = v17.v16
ROOT = v17.ROOT
BASELINE_RELATIVE_DIR = "verified_construction_core/2026-08-20-preview-v0.17"
BASELINE_MANIFEST_SHA256 = (
    "49cf79185742a2bd718a83683c924574ba8db4de1289d1228e56c5865154c8fc"
)
SCHEMA_VERSION = "datacenter-atlas-v018-reviewed-batch-v1"
SCHEMA_VERSION_V2 = "datacenter-atlas-v018-reviewed-batch-v2"
SCHEMA_VERSION_V3 = "datacenter-atlas-v018-reviewed-batch-v3"
CONTRACT_KEYS = frozenset(
    {
        "schema_version",
        "batch_id",
        "base_preview_manifest_sha256",
        "lifecycle_reference_date",
        "geometry_identity_reviewed_at",
        "sources",
        "acceptances",
    }
)
CONTRACT_KEYS_V2 = CONTRACT_KEYS | {"baseline_corrections"}
CONTRACT_KEYS_V3 = CONTRACT_KEYS_V2 | {"blind_review"}
LIFECYCLE_REFERENCE_DATE = date(2026, 8, 20)
TARGET_ADDITIONAL_SITES = 100
LOCATION_BASES = frozenset(
    {
        "first_party_site_coordinate",
        "official_address_geocode",
        "official_named_site_feature",
        "official_parcel",
        "community_named_site_feature",
        "authoritative_site_boundary",
    }
)
USE_SCOPES = frozenset(
    {"campus_locator", "project_locator", "reviewed_site_locator", "official_boundary"}
)
SEMANTIC_FIELDS = frozenset(
    {
        "geometry_source_entity_kind",
        "geometry_derivation",
        "geometry_method",
        "geometry_scope_class",
        "geometry_authority_class",
        "geometry_use_scope",
        "precision_scope",
        "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason",
    }
)
GEOMETRY_RECORD_KEYS = frozenset(
    {
        "project_stable_key",
        "parent_campus_stable_key",
        "geometry",
        "display_anchor",
        "geometry_source_ids",
        "identity_source_ids",
        "location_basis",
        "semantics",
    }
)
# Host-estate locality context is accepted ONLY through a pinned baseline
# correction of an inherited row, never as the locator of a new acceptance.
BASELINE_CORRECTION_LOCATION_BASES = frozenset({"host_estate_locality_context"})
BASELINE_CORRECTION_ENTITY_KINDS = frozenset({"host_estate"})
BASELINE_CORRECTION_USE_SCOPES = frozenset({"host_estate_context"})
HOST_ESTATE_CONTEXT_POSTURE = (
    "recent_authoritative_physical_observation_plus_host_estate_context_only"
)
BASELINE_CORRECTION_KEYS = frozenset(
    {
        "correction_id",
        "physical_site_stable_key",
        "project_stable_key",
        "frozen_rows",
        "geometry",
        "identity_source_id",
        "evidence_source_ids",
        "reason",
    }
)
SUPERSEDES_KEYS = frozenset(
    {
        "source_path",
        "source_file_sha256",
        "source_file_bytes",
        "evidence_pointer",
        "evidence_record_sha256",
        "evidence_source_id",
        "evidence_id",
        "geometry_pointer",
        "geometry_record_sha256",
        "locator_id",
        "frozen_baseline_rows",
        "inherited_unchanged_through",
        "correction_reason",
        "frozen_artifact_mutated",
    }
)
# Optional supersedes key for a frozen locator whose site binds more than one
# geometry capture (e.g. an OSM multi-way union). Absent for single-capture rows.
SUPERSEDES_OPTIONAL_KEYS = frozenset({"additional_superseded_evidence"})
ADDITIONAL_SUPERSEDED_KEYS = frozenset(
    {
        "evidence_pointer",
        "evidence_record_sha256",
        "evidence_source_id",
        "evidence_id",
        "replacement_source_id",
    }
)
FROZEN_ROWS_KEYS = frozenset(
    {
        "release_path",
        "manifest_sha256",
        "projects_csv",
        "sites_csv",
        "evidence_csv",
        "sites_geojson",
    }
)
FROZEN_ROWS_OPTIONAL_KEYS = frozenset({"additional_evidence_csv"})
FROZEN_ROW_TABLES = (
    ("projects_csv", "projects", "project_stable_key"),
    ("sites_csv", "sites", "physical_site_stable_key"),
    ("evidence_csv", "evidence", "evidence_id"),
)
CAPTURE_FIELDS = (
    "kind",
    "source_url",
    "publisher",
    "source_family",
    "license",
    "attribution",
    "published_at",
    "retrieved_at",
    "content_hash",
)
BINDING_POINTERS = (
    ("evidence_pointer", "evidence_record_sha256"),
    ("project_pointer", "project_sha256"),
    ("campus_pointer", "campus_sha256"),
    ("lifecycle_pointer", "lifecycle_sha256"),
    ("acceptance_pointer", "acceptance_sha256"),
)
CORRECTION_COUNT_KEYS = frozenset(
    {
        "physical_sites",
        "projects",
        "evidence",
        "reviewed_site_locator_projects",
        "host_estate_context_projects",
        "official_boundary_projects",
        "countries",
        "non_us_sites",
    }
)
DRAFT_MANIFEST_FORMAT_V1 = "datacenter-atlas-verified-construction-core-v018-draft-v1"
DRAFT_MANIFEST_FORMAT_V2 = "datacenter-atlas-verified-construction-core-v018-draft-v2"
DRAFT_MANIFEST_FORMAT_V3 = "datacenter-atlas-verified-construction-core-v018-draft-v3"
# A v2 correction's inherited-through release keeps exactly its v2 formats; a
# v3 contract may also name a v3 draft. Any v0.18 draft may be a population.
INHERITED_THROUGH_FORMATS_V2 = frozenset(
    {DRAFT_MANIFEST_FORMAT_V1, DRAFT_MANIFEST_FORMAT_V2}
)
INHERITED_THROUGH_FORMATS_V3 = INHERITED_THROUGH_FORMATS_V2 | {DRAFT_MANIFEST_FORMAT_V3}
# Schema v3 only: a pinned baseline withdrawal removes one inherited v0.17 project
# (with its single-project site, feature and the evidence rows only it used) from
# the selection. It never asserts a physical status for the withdrawn project.
BASELINE_WITHDRAWAL_KEYS = frozenset(
    {
        "withdrawal_id",
        "physical_site_stable_key",
        "project_stable_key",
        "frozen_rows",
        "record",
        "reason",
    }
)
BASELINE_WITHDRAWAL_RECORD_SCHEMA = "datacenter-atlas-v018-baseline-withdrawal-v1"
BASELINE_WITHDRAWAL_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "withdrawal_id",
        "reviewed_at",
        "lifecycle_reference_date",
        "accepted_additional_sites",
        "project_stable_key",
        "physical_site_stable_key",
        "decision",
        "withdrawal_basis",
        "claim_boundary",
        "frozen_baseline_rows",
        "inherited_unchanged_through",
        "withdrawn_observation_binding",
        "review_basis",
        "count_effect",
        "shared_capture_rows",
        "withdrawal_reason",
    }
)
# A withdrawal record acknowledges every other frozen evidence row that shares a
# withdrawn row's source capture (the same source URL and content hash): a
# withdrawal neither changes nor re-reviews those rows.
SHARED_CAPTURE_KEYS = frozenset({"rows", "statement"})
WITHDRAWAL_SHARED_CAPTURE_GATE = "withdrawal_shared_capture_review"
BASELINE_WITHDRAWAL_DECISION = "withdraw_from_selection"
BASELINE_WITHDRAWAL_BASES = frozenset(
    {"status_evidence_does_not_meet_contract", "identity_evidence_does_not_meet_contract"}
)
# The exact claim boundary every withdrawal record carries, besides its
# ``statement`` text: a withdrawal removes a selection, never states a status.
BASELINE_WITHDRAWAL_CLAIM_BOUNDARY: Mapping[str, Any] = MappingProxyType(
    {
        "asserted_physical_status": None,
        "physical_status_on_lifecycle_reference_date": "unknown",
        "asserts_not_under_construction": False,
        "asserts_paused": False,
        "asserts_cancelled": False,
        "asserts_completed": False,
    }
)
# Checkpoint-independent count effect of one withdrawal. The country effect
# depends on the other selected sites and is derived for the checkpoint only.
WITHDRAWAL_COUNT_KEYS = frozenset(
    {
        "physical_sites",
        "projects",
        "evidence",
        "non_us_sites",
        "reviewed_site_locator_projects",
        "host_estate_context_projects",
        "official_boundary_projects",
    }
)
# Schema v3: the pinned, pre-registered blind review of the eligible population.
BLIND_REVIEW_PREREGISTRATION_SCHEMA = "datacenter-atlas-v018-blind-review-preregistration-v1"
BLIND_REVIEW_RESULTS_SCHEMA = "datacenter-atlas-v018-blind-review-results-v1"
BLIND_REVIEW_SEED_PREFIX = "datacenter-atlas-blind-review-v1"
BLIND_REVIEW_SAMPLE_SIZE = 20
BLIND_REVIEW_REQUIRED_AGREEMENTS = 19
BLIND_REVIEW_POPULATION_SCOPE = (
    "all expanded projects, including inherited baseline and reviewed draft additions"
)
# The only accepted pre-registration of each population, keyed by the SHA-256 of
# the population release's manifest. A contract cannot choose another sample of a
# registered population; a new population needs a new, separately published
# pre-registration added here by a reviewed change.
BLIND_REVIEW_PREREGISTRATIONS: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        "515159b79bb7263fe1cf88c054a75bfdbd817acba2ae6bc3452f004cf7e80208": MappingProxyType(
            {
                "path": "definitions/verified-construction-core-v0.18-blind-review-preregistration-v1.json",
                "bytes": 12141,
                "sha256": "df104f1d7a59af535ab919a9ab842988afbae039970eb8808eb228863f8f8dd3",
            }
        ),
    }
)
# The blind-reviewed claims of an eligible project: its identity, its construction
# status and its location, with its site's identity and geometry. Other fields
# (imagery outcomes, evidence, semantics, posture) are not blind-reviewed.
BLIND_REVIEW_PROJECT_CLAIM_FIELDS = (
    "physical_site_stable_key",
    "name",
    "country",
    "country_iso_a2",
    "geometry_json",
    "last_observed_physical_status",
    "status_as_of",
)
BLIND_REVIEW_SITE_CLAIM_FIELDS = ("name", "country", "country_iso_a2", "geometry_json")
BLIND_REVIEW_WINDOW = (LIFECYCLE_REFERENCE_DATE - timedelta(days=90), LIFECYCLE_REFERENCE_DATE)
BLIND_REVIEW_INPUTS = ("project_name", "campus_name", "country", "physical_observation_window")
PREREGISTRATION_KEYS = frozenset(
    {"schema_version", "registered_at", "purpose", "population", "sampling", "protocol", "sample"}
)
PREREGISTRATION_POPULATION_KEYS = frozenset(
    {
        "release_path",
        "manifest_sha256",
        "published_in_commit",
        "eligible_project_count",
        "eligible_project_keys_sha256",
        "population_scope",
    }
)
PREREGISTRATION_SAMPLING_KEYS = frozenset(
    {"method", "seed_material", "seed_sha256", "sample_size", "formula_fixed_before_draw"}
)
PREREGISTRATION_PROTOCOL_KEYS = frozenset(
    {
        "lifecycle_reference_date",
        "physical_observation_window",
        "reviewers",
        "blind_inputs",
        "withheld_from_reviewers",
        "reviewer_outputs",
        "agreement_rules",
        "after_review",
    }
)
PREREGISTRATION_TEXT_BLOCKS = (
    ("reviewer_outputs", frozenset({"construction_determination", "location", "identity_notes"})),
    ("agreement_rules", frozenset({"construction", "location", "agreement", "gate"})),
)
RESULTS_KEYS = frozenset(
    {
        "schema_version",
        "recorded_at",
        "preregistration",
        "population",
        "reviews",
        "comparison",
        "totals",
        "disclosures",
    }
)
SESSION_KEYS = frozenset(
    {
        "position",
        "project_stable_key",
        "reviewer_session_id",
        "session_sequence",
        "session_status",
        "reviewed_at",
        "counted",
    }
)
REVIEW_KEYS = SESSION_KEYS | {
    "construction_determination",
    "construction_evidence",
    "successor_check",
    "location",
    "identity_notes",
    "blindness_attestation",
}
UNCOUNTED_SESSION_KEYS = frozenset({"uncounted_reason", "counted_session_id"})
ABORTED_SESSION_KEYS = SESSION_KEYS | UNCOUNTED_SESSION_KEYS | {"abort_notes"}
UNCOUNTED_REASONS = frozenset({"aborted", "blindness_breach", "later_duplicate"})
REVIEW_EVIDENCE_KEYS = frozenset(
    {"source_url", "observation_date", "literal_pointer", "capture_sha256"}
)
REVIEW_EVIDENCE_OPTIONAL_KEYS = frozenset({"title", "publisher", "retrieved_at", "note"})
REVIEW_LOCATION_KEYS = frozenset({"status", "longitude", "latitude", "method", "source_url"})
REVIEW_LOCATION_OPTIONAL_KEYS = frozenset({"literal_pointer", "capture_sha256", "notes"})
COMPARISON_KEYS = frozenset(
    {
        "position",
        "project_stable_key",
        "construction_agrees",
        "location_distance_m",
        "location_rule",
        "adjudication",
        "agreement",
    }
)
ADJUDICATION_KEYS = frozenset({"adjudicated_by", "adjudicated_at", "reason"})
BLIND_REVIEW_COUNTED_SESSION_RULE = (
    "At each position the counted session is the completed blind session with the "
    "lowest session_sequence; a blind session attests no Atlas access and cites no "
    "Atlas surface in its evidence or location URLs. Every other session is recorded "
    "uncounted with a machine-checked reason: aborted (no reviewer output), "
    "blindness_breach (attested Atlas access or a cited Atlas surface) or "
    "later_duplicate (a blind session started after the counted one)."
)
# Atlas surfaces a blind session must not cite: the public site, the repository
# and any fork or clone of it on GitHub, its raw, codeload, API and jsDelivr
# mirrors, and archived copies of any of these (matched inside the whole URL,
# case-insensitively, after percent-decoding).
ATLAS_SURFACE_URL_PATTERNS = (
    re.compile(r"[a-z0-9-]+\.github\.io/datacenter[-_]atlas(?![a-z0-9_-])"),
    re.compile(
        r"github(?:usercontent)?\.com/(?:repos/)?[a-z0-9_.-]+/datacenter[-_]atlas(?![a-z0-9_-])"
    ),
    re.compile(r"cdn\.jsdelivr\.net/gh/[a-z0-9_.-]+/datacenter[-_]atlas(?![a-z0-9_-])"),
)
CONSTRUCTION_DETERMINATIONS = frozenset(
    {"under_construction_in_window", "not_under_construction_in_window", "unable_to_verify"}
)
SUCCESSOR_CHECK_STATUSES = frozenset(
    {"none_found_on_or_before_cutoff", "found_on_or_before_cutoff", "not_checked"}
)
LOCATION_RULES = (
    "inside",
    "within_1000m",
    "adjudicated_same_campus",
    "adjudicated_different_campus",
    "beyond_3000m",
    "unable_to_locate",
)
ADJUDICATED_LOCATION_RULES = frozenset(
    {"adjudicated_same_campus", "adjudicated_different_campus"}
)
AGREEING_LOCATION_RULES = frozenset({"inside", "within_1000m", "adjudicated_same_campus"})
LOCATION_AGREEMENT_METRES = 1000.0
LOCATION_ADJUDICATION_METRES = 3000.0
DISTANCE_TOLERANCE_METRES = 5.0
DISTANCE_TOLERANCE_FRACTION = 0.01
WGS84_A = 6378137.0
WGS84_F = 1 / 298.257223563
WGS84_B = WGS84_A * (1 - WGS84_F)
WGS84_MEAN_RADIUS = (2 * WGS84_A + WGS84_B) / 3
# The largest meridional radius of curvature (at the poles) and the equatorial
# radius bound the length of any longitude/latitude-straight edge from above.
WGS84_MAX_MERIDIONAL_RADIUS = WGS84_A / math.sqrt(1 - WGS84_F * (2 - WGS84_F))
BLIND_REVIEW_LOCATION_METHOD = (
    "Against the site geometry of the pre-registered population release, in WGS84: "
    "a point covered by a Polygon/MultiPolygon in longitude/latitude "
    "(RFC 7946 straight edges, boundary inclusive, holes excluded) or equal to a "
    "Point is inside at 0 m; otherwise the minimum ellipsoidal geodesic distance "
    "(Vincenty inverse, converged to 1e-12 rad; mean-sphere great circle if a "
    "nearly antipodal pair does not converge) to the Point or to any ring edge, "
    "minimized along each edge by golden-section search with both endpoints "
    "checked. within_1000m: 0 < d <= 1000 m; adjudication band: 1000 < d <= "
    "3000 m; beyond_3000m: d > 3000 m. The rule is classified from the recomputed "
    "distance; a recorded distance must agree with it within max(5 m, 1 %) and lie "
    "in the same band (exactly 0 m for inside)."
)
# Every key of a correction's preservation_invariants is machine-checked: the
# required keys against the frozen rows and records, these optional ones below.
OPTIONAL_PRESERVATION_INVARIANTS = frozenset(
    {
        "osm_way_version_unchanged",
        "intersecting_site_rows_unchanged",
        "additional_superseded_captures_unchanged",
        "display_anchor_outside_geometry",
    }
)
ADDITIONAL_CAPTURE_INVARIANT_KEYS = frozenset(
    {
        "evidence_id",
        "raw_evidence_body_sha256_unchanged",
        "raw_capture_retrieved_at_unchanged",
    }
)
ISO_A2_CODES = frozenset(
    """
AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ
BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM
DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS
GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN
KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ
MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM
PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV
SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI
VN VU WF WS YE YT ZA ZM ZW
""".split()
)


class DraftValidationError(core.VerifiedConstructionCoreError):
    """A reviewed input or draft invariant is missing or inconsistent."""


TABLE_FIELDS = {
    "projects": core.PROJECT_FIELDS,
    "sites": core.SITE_FIELDS,
    "evidence": core.EVIDENCE_FIELDS,
}


@dataclass(frozen=True)
class ReviewPins:
    contract_sha256: str
    source_sha256: Mapping[str, str]
    acceptance_sha256: Mapping[str, str]
    # One independent pin per v2 baseline correction_id; empty for v1 contracts.
    baseline_correction_sha256: Mapping[str, str] = MappingProxyType({})
    # canonical_sha256 of a v3 contract's blind_review entry; None for v1 and v2.
    blind_review_sha256: str | None = None
    # One independent pin per v3 baseline withdrawal_id; empty unless the v3
    # contract carries baseline_withdrawals.
    baseline_withdrawal_sha256: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True)
class ValidatedBatch:
    root: Path
    contract_path: Path
    pins: ReviewPins
    contract: dict[str, Any]
    baseline: dict[str, Any]
    sources: dict[str, dict[str, Any]]
    acceptances: tuple[dict[str, Any], ...]
    baseline_corrections: tuple[dict[str, Any], ...] = ()
    # The recomputed v3 blind-review result; None for v1 and v2 contracts.
    blind_review: Mapping[str, Any] | None = None
    # Validated v3 baseline withdrawals; empty for v1, v2 and v3 without them.
    baseline_withdrawals: tuple[dict[str, Any], ...] = ()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(core._json_bytes(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DraftValidationError(message)


def _keys(
    value: Any, expected: set[str] | frozenset[str], label: str
) -> dict[str, Any]:
    _require(
        isinstance(value, dict) and set(value) == set(expected), f"{label} keys differ"
    )
    return value


def _text(value: Any, label: str) -> str:
    _require(
        isinstance(value, str) and bool(value.strip()), f"{label} must be nonempty text"
    )
    return value


def _hash(value: Any, label: str) -> str:
    _require(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
        f"{label} is not SHA-256",
    )
    return value


def _calendar(value: Any, label: str) -> date:
    _require(
        isinstance(value, str)
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None,
        f"{label} must be YYYY-MM-DD",
    )
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DraftValidationError(f"invalid {label}") from exc


def _unique_text(values: Any, label: str, *, empty: bool = False) -> list[str]:
    _require(
        isinstance(values, list) and (empty or bool(values)), f"{label} must be a list"
    )
    for value in values:
        _text(value, label)
    _require(len(values) == len(set(values)), f"duplicate {label}")
    return values


def _portable_path(root: Path, relative: Any, label: str) -> Path:
    _text(relative, label)
    parts = Path(relative)
    _require(
        not parts.is_absolute() and ".." not in parts.parts and "." not in parts.parts,
        f"nonportable {label}",
    )
    _require(
        parts.as_posix() == relative and bool(parts.parts), f"noncanonical {label}"
    )
    path = root / parts
    _require(path.resolve().is_relative_to(root.resolve()), f"{label} escapes root")
    cursor = root
    for part in parts.parts:
        cursor /= part
        _require(not cursor.is_symlink(), f"symlink in {label}")
    return path


def _read_pinned(path: Path, expected_sha256: str, size: int | None = None) -> bytes:
    _hash(expected_sha256, str(path))
    _require(not path.is_symlink() and path.is_file(), f"missing regular input: {path}")
    data = path.read_bytes()
    _require(
        hashlib.sha256(data).hexdigest() == expected_sha256,
        f"input SHA-256 differs: {path}",
    )
    if size is not None:
        _require(
            type(size) is int and size >= 0 and len(data) == size,
            f"input byte count differs: {path}",
        )
    return data


def _json(data: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            _require(key not in result, f"duplicate JSON key in {label}: {key}")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise DraftValidationError(f"nonfinite JSON in {label}: {value}")

    try:
        return json.loads(
            data, object_pairs_hook=pairs, parse_constant=invalid_constant
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise DraftValidationError(f"invalid JSON: {label}") from exc


def _pointer(document: Any, pointer: Any) -> Any:
    _require(
        isinstance(pointer, str) and (pointer == "" or pointer.startswith("/")),
        "invalid JSON pointer",
    )
    current = document
    for token in pointer.split("/")[1:]:
        _require(re.search(r"~(?![01])", token) is None, "invalid JSON pointer escape")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            _require(token in current, f"JSON pointer missing: {pointer}")
            current = current[token]
        elif isinstance(current, list):
            _require(
                re.fullmatch(r"0|[1-9][0-9]*", token) is not None,
                "invalid JSON pointer array index",
            )
            index = int(token)
            _require(index < len(current), f"JSON pointer outside array: {pointer}")
            current = current[index]
        else:
            raise DraftValidationError(f"JSON pointer crosses a scalar: {pointer}")
    return current


def _record(
    sources: Mapping[str, Any], source_id: str, pointer: str, digest: str, label: str
) -> dict[str, Any]:
    _require(source_id in sources, f"unbound {label} source: {source_id}")
    value = _pointer(sources[source_id]["document"], pointer)
    _require(isinstance(value, dict), f"{label} is not an object")
    _require(
        canonical_sha256(value) == _hash(digest, label),
        f"{label} record SHA-256 differs",
    )
    return value


def _load_baseline(root: Path) -> dict[str, Any]:
    directory = _portable_path(root, BASELINE_RELATIVE_DIR, "baseline path")
    raw_manifest = _read_pinned(directory / "manifest.json", BASELINE_MANIFEST_SHA256)
    manifest = _json(raw_manifest, "baseline manifest")
    _require(
        manifest["counts"]["physical_sites"] == 100
        and manifest["counts"]["projects"] == 103,
        "frozen baseline counts differ",
    )
    expected_checksum = f"{BASELINE_MANIFEST_SHA256}  manifest.json\n".encode()
    checksum = directory / "manifest.sha256"
    _require(
        not checksum.is_symlink()
        and checksum.is_file()
        and checksum.read_bytes() == expected_checksum,
        "baseline manifest checksum differs",
    )
    files = {}
    for name, spec in manifest["files"].items():
        _require(Path(name).name == name, "invalid baseline member")
        files[name] = _read_pinned(directory / name, spec["sha256"], spec["bytes"])
    _require(
        {path.name for path in directory.iterdir()}
        == set(files) | {"manifest.json", "manifest.sha256"},
        "baseline file inventory differs",
    )
    tables = {
        name: core._load_csv(directory / f"{name}.csv", fields)
        for name, fields in (
            ("projects", core.PROJECT_FIELDS),
            ("sites", core.SITE_FIELDS),
            ("evidence", core.EVIDENCE_FIELDS),
        )
    }
    _require(
        len(tables["sites"]) == 100 and len(tables["projects"]) == 103,
        "baseline table counts differ",
    )
    return {"manifest": manifest, "files": files, **tables}


def _date_only(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None


def _source_evidence(
    evidence: Any, label: str, *, inherited_date_only_retrieval: bool = False
) -> dict[str, Any]:
    """Project curated evidence; date-only retrieval only for a reused v2 capture.

    ``inherited_date_only_retrieval`` is set solely by ``validate_batch`` for a
    v2 source whose literal ``retrieved_at`` is a calendar date. That source is
    later required to be a baseline correction's reused frozen capture; every
    other source keeps the timezone-bearing retrieval requirement.
    """
    _require(isinstance(evidence, dict), f"{label} evidence is not an object")
    for field in (
        "key",
        "kind",
        "title",
        "source_url",
        "publisher",
        "source_family",
        "license",
        "attribution",
        "retrieved_at",
    ):
        _text(evidence.get(field), f"{label} evidence {field}")
    _hash(evidence.get("content_hash"), f"{label} content hash")
    url = urlsplit(evidence["source_url"])
    _require(
        url.scheme in {"https", "http"}
        and bool(url.hostname)
        and not url.username
        and not url.password,
        f"invalid {label} source URL",
    )
    if inherited_date_only_retrieval:
        # A reused frozen capture keeps its literal calendar date; no time of
        # day or timezone is invented, so comparisons below are day-level.
        _require(
            _date_only(evidence["retrieved_at"]),
            f"{label} inherited retrieval must be a calendar date",
        )
        retrieved = None
        retrieval_day = _calendar(
            evidence["retrieved_at"], f"{label} inherited retrieval date"
        )
    else:
        try:
            retrieved = datetime.fromisoformat(
                evidence["retrieved_at"].replace("Z", "+00:00")
            )
            _require(retrieved.tzinfo is not None, f"{label} retrieval needs timezone")
        except ValueError as exc:
            raise DraftValidationError(f"invalid {label} retrieval timestamp") from exc
        retrieval_day = retrieved.date()
    _require(
        "published_at" in evidence, f"{label} publication date must be explicit or null"
    )
    if evidence["published_at"] is not None:
        publication_text = _text(evidence["published_at"], f"{label} publication date")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", publication_text):
            publication_day = _calendar(publication_text, f"{label} publication date")
            publication_precedes_retrieval = publication_day <= retrieval_day
        else:
            _require(
                re.match(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", publication_text)
                is not None,
                f"invalid {label} publication datetime",
            )
            try:
                publication_time = datetime.fromisoformat(
                    publication_text.replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise DraftValidationError(
                    f"invalid {label} publication datetime"
                ) from exc
            # Preserve timezone-free source values without inventing a timezone.
            publication_precedes_retrieval = (
                publication_time <= retrieved
                if publication_time.tzinfo is not None and retrieved is not None
                else publication_time.date() <= retrieval_day
            )
        _require(
            publication_precedes_retrieval,
            f"{label} publication follows retrieval",
        )
    identifier = core.atlas_stable_id(
        "evidence", "curated-official", evidence["key"], evidence["content_hash"]
    )
    return core._v07_evidence_projection({**evidence, "evidence_id": identifier})


def _point(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(
            type(number) in {int, float} and math.isfinite(number) for number in value
        )
        and -180 <= value[0] <= 180
        and -90 <= value[1] <= 90
    )


def _ring(value: Any) -> bool:
    if not (
        isinstance(value, list)
        and len(value) >= 4
        and all(_point(point) for point in value)
        and value[0] == value[-1]
    ):
        return False
    if len({tuple(point) for point in value[:-1]}) != len(value) - 1:
        return False
    segments = list(zip(value, value[1:]))
    for index, (a, b) in enumerate(segments):
        for other_index, (c, d) in enumerate(segments):
            if other_index <= index + 1 or (
                index == 0 and other_index == len(segments) - 1
            ):
                continue
            if _segments_intersect(a, b, c, d):
                return False
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in segments)) > 1e-15


def _segments_intersect(a: list, b: list, c: list, d: list) -> bool:
    def side(p: list, q: list, r: list) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_segment(p: list, q: list, r: list) -> bool:
        return (
            abs(side(p, q, r)) < 1e-12
            and min(p[0], q[0]) <= r[0] <= max(p[0], q[0])
            and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])
        )

    orientations = side(a, b, c), side(a, b, d), side(c, d, a), side(c, d, b)
    return (
        (
            orientations[0] * orientations[1] < 0
            and orientations[2] * orientations[3] < 0
        )
        or on_segment(a, b, c)
        or on_segment(a, b, d)
        or on_segment(c, d, a)
        or on_segment(c, d, b)
    )


def _inside_ring(point: list[float], ring: list[list[float]]) -> bool:
    x, y = point
    inside = False
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        cross = (x - ax) * (by - ay) - (y - ay) * (bx - ax)
        if (
            abs(cross) < 1e-12
            and min(ax, bx) <= x <= max(ax, bx)
            and min(ay, by) <= y <= max(ay, by)
        ):
            return True
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def _anchor_in_polygons(anchor: list[float], polygons: list) -> bool:
    return any(
        _inside_ring(anchor, polygon[0])
        and not any(_inside_ring(anchor, hole) for hole in polygon[1:])
        for polygon in polygons
    )


def _geometry_shape(
    record: Any,
    label: str = "geometry record",
    *,
    exterior_anchor_allowed: bool = False,
) -> str:
    """Structural geometry/anchor checks shared by acceptances and corrections.

    ``exterior_anchor_allowed`` is set ONLY by the baseline-correction validator,
    which then requires the anchor to equal the frozen row and the record to
    declare the exterior anchor as a machine-checked preservation invariant.
    """
    _keys(record, GEOMETRY_RECORD_KEYS, label)
    geometry = _keys(record["geometry"], {"type", "coordinates"}, "geometry")
    anchor = _keys(record["display_anchor"], {"type", "coordinates"}, "display anchor")
    _require(
        anchor["type"] == "Point" and _point(anchor["coordinates"]),
        "invalid display anchor",
    )
    kind, coordinates = geometry["type"], geometry["coordinates"]
    _require(kind in {"Point", "Polygon", "MultiPolygon"}, "unsupported geometry type")
    if kind == "Point":
        _require(
            _point(coordinates) and coordinates == anchor["coordinates"],
            "Point display anchor differs",
        )
    else:
        polygons = [coordinates] if kind == "Polygon" else coordinates
        _require(
            isinstance(polygons, list) and bool(polygons), "empty polygon geometry"
        )
        for polygon in polygons:
            _require(
                isinstance(polygon, list)
                and bool(polygon)
                and all(_ring(ring) for ring in polygon),
                "invalid or degenerate polygon ring",
            )
            _require(
                all(
                    abs(a[0] - b[0]) <= 180
                    for ring in polygon
                    for a, b in zip(ring, ring[1:])
                ),
                "antimeridian polygon requires separate review support",
            )
            for index, ring in enumerate(polygon):
                if index:
                    _require(
                        _inside_ring(ring[0], polygon[0]),
                        "polygon hole lies outside exterior",
                    )
                for other in polygon[index + 1 :]:
                    _require(
                        not any(
                            _segments_intersect(a, b, c, d)
                            for a, b in zip(ring, ring[1:])
                            for c, d in zip(other, other[1:])
                        ),
                        "polygon rings intersect",
                    )
                    if index:
                        _require(
                            not _inside_ring(ring[0], other)
                            and not _inside_ring(other[0], ring),
                            "polygon holes overlap",
                        )
        _require(
            exterior_anchor_allowed
            or _anchor_in_polygons(anchor["coordinates"], polygons),
            "polygon display anchor is outside its geometry",
        )
    return kind


def _anchor_inside_geometry(record: Mapping[str, Any]) -> bool:
    """True for a Point geometry (anchor equals it) or an anchor inside a polygon."""
    geometry = record["geometry"]
    if geometry["type"] == "Point":
        return True
    polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )
    return _anchor_in_polygons(record["display_anchor"]["coordinates"], polygons)


def _host_estate_semantics(record: Mapping[str, Any], semantics: Any) -> bool:
    basis = record.get("location_basis")
    return (
        (isinstance(basis, str) and basis in BASELINE_CORRECTION_LOCATION_BASES)
        or (
            isinstance(semantics, Mapping)
            and (
                semantics.get("geometry_source_entity_kind")
                in BASELINE_CORRECTION_ENTITY_KINDS
                or semantics.get("geometry_use_scope")
                in BASELINE_CORRECTION_USE_SCOPES
            )
        )
    )


def _geometry(record: dict[str, Any]) -> None:
    """Validate an ACCEPTANCE locator; host-estate context is always rejected."""
    kind = _geometry_shape(record)
    semantics = _keys(record["semantics"], SEMANTIC_FIELDS, "geometry semantics")
    for field in SEMANTIC_FIELDS - {
        "horizontal_uncertainty_metres",
        "horizontal_uncertainty_unknown_reason",
    }:
        _text(semantics[field], f"geometry semantics {field}")
    _require(
        not _host_estate_semantics(record, semantics),
        "host-estate locality context is accepted only through a pinned baseline "
        "correction, never as an acceptance locator",
    )
    _require(
        isinstance(record["location_basis"], str)
        and record["location_basis"] in LOCATION_BASES,
        "unsupported location basis; locality centroids are not accepted",
    )
    _require(
        semantics["geometry_source_entity_kind"] in {"project", "campus"},
        "geometry entity scope differs",
    )
    _require(
        semantics["geometry_authority_class"]
        in {"official_source", "community_source"},
        "geometry authority differs",
    )
    _require(
        semantics["geometry_use_scope"] in USE_SCOPES, "geometry use scope differs"
    )
    boundary = semantics["geometry_use_scope"] == "official_boundary"
    _require(
        boundary == (record["location_basis"] == "authoritative_site_boundary"),
        "boundary evidence/semantics differ",
    )
    if boundary:
        _require(
            kind in {"Polygon", "MultiPolygon"}
            and semantics["geometry_authority_class"] == "official_source",
            "official boundary requires official polygon evidence",
        )
    if record["location_basis"] == "community_named_site_feature":
        _require(
            semantics["geometry_authority_class"] == "community_source",
            "community geometry promoted to official",
        )
    else:
        _require(
            semantics["geometry_authority_class"] == "official_source",
            "official location basis has nonofficial authority",
        )
    uncertainty = semantics["horizontal_uncertainty_metres"]
    reason = semantics["horizontal_uncertainty_unknown_reason"]
    if uncertainty is None:
        _text(reason, "unknown horizontal uncertainty reason")
    else:
        _require(
            type(uncertainty) in {int, float}
            and math.isfinite(uncertainty)
            and uncertainty > 0
            and reason == "",
            "numeric uncertainty/reason differs",
        )


def _verification_posture(authority: str, use_scope: str) -> str:
    if use_scope in BASELINE_CORRECTION_USE_SCOPES:
        return HOST_ESTATE_CONTEXT_POSTURE
    return core._verification_posture(authority, use_scope)


def _is_host_estate_context(row: Mapping[str, Any]) -> bool:
    return row.get("geometry_use_scope") in BASELINE_CORRECTION_USE_SCOPES


def _is_reviewed_locator(row: Mapping[str, Any]) -> bool:
    return not _is_host_estate_context(row) and core._is_reviewed_locator(row)


def _json_cell(value: Any) -> str:
    return core._json_bytes(value).decode().strip()


def _json_field(text: Any, label: str) -> Any:
    _require(isinstance(text, str), f"{label} is not text")
    return _json(text.encode(), label)


def _csv_line(row: Mapping[str, Any], fields: Sequence[str]) -> bytes:
    """One CSV data line, without its newline, exactly as the table writer emits it."""
    line = core._csv_bytes([row], fields).split(b"\n", 1)[1]
    _require(
        line.count(b"\n") == 1 and line.endswith(b"\n") and b"\r" not in line,
        "CSV row would span lines",
    )
    return line[:-1]


def _csv_lines(raw: bytes, count: int, label: str) -> list[bytes]:
    lines = raw.split(b"\n")
    _require(
        len(lines) == count + 2 and lines[-1] == b"" and b"\r" not in raw,
        f"{label} line numbering is ambiguous",
    )
    return lines


def _pinned_v017_input(
    baseline: Mapping[str, Any], path: Any, sha256: Any, size: Any
) -> bool:
    inputs = baseline["manifest"].get("portable_source_inputs")
    return isinstance(inputs, list) and any(
        isinstance(item, dict)
        and item.get("path") == path
        and item.get("sha256") == sha256
        and type(item.get("bytes")) is int
        and item.get("bytes") == size
        for item in inputs
    )


def _locate_frozen_row(
    spec: Any, baseline: Mapping[str, Any], table: str, id_field: str
) -> dict[str, Any]:
    """Hash-check one frozen v0.17 data line named by line number and identifier."""
    spec = _keys(
        spec,
        {"file_line_number", id_field, "row_canonical_sha256", "raw_line_sha256"},
        f"frozen {table} row",
    )
    rows = baseline[table]
    lines = _csv_lines(
        baseline["files"][f"{table}.csv"], len(rows), f"frozen {table}.csv"
    )
    number = spec["file_line_number"]
    _require(
        type(number) is int and 2 <= number <= len(rows) + 1,
        f"frozen {table} line number differs",
    )
    row = rows[number - 2]
    identifier = _text(spec[id_field], f"frozen {table} identifier")
    _require(
        row[id_field] == identifier
        and sum(item[id_field] == identifier for item in rows) == 1,
        f"frozen {table} row identity differs",
    )
    _require(
        canonical_sha256(row)
        == _hash(spec["row_canonical_sha256"], f"frozen {table} row hash"),
        f"frozen {table} row SHA-256 differs",
    )
    raw = lines[number - 1]
    _require(
        hashlib.sha256(raw).hexdigest()
        == _hash(spec["raw_line_sha256"], f"frozen {table} raw line hash"),
        f"frozen {table} raw line SHA-256 differs",
    )
    _require(
        _csv_line(row, TABLE_FIELDS[table]) == raw,
        f"frozen {table} row does not reproduce its raw line",
    )
    return {"index": number - 2, "line": number, "row": row, "raw": raw}


def _frozen_rows(
    frozen: Any, baseline: Mapping[str, Any], project_key: str, site_key: str
) -> dict[str, Any]:
    """Locate and hash-check the frozen v0.17 rows and feature a correction names.

    ``additional_evidence_csv`` (optional, nonempty when present) names further
    frozen geometry evidence rows of the same project that the correction also
    supersedes, for a frozen site that binds several geometry captures.
    """
    _require(
        isinstance(frozen, dict)
        and FROZEN_ROWS_KEYS <= set(frozen)
        and set(frozen) <= FROZEN_ROWS_KEYS | FROZEN_ROWS_OPTIONAL_KEYS,
        "baseline correction frozen rows keys differ",
    )
    _require(
        frozen["release_path"] == BASELINE_RELATIVE_DIR
        and frozen["manifest_sha256"] == BASELINE_MANIFEST_SHA256,
        "baseline correction must name rows of the pinned v0.17 manifest",
    )
    located: dict[str, Any] = {}
    for key, table, id_field in FROZEN_ROW_TABLES:
        located[table] = _locate_frozen_row(frozen[key], baseline, table, id_field)
    additional_specs = frozen.get("additional_evidence_csv", None)
    _require(
        "additional_evidence_csv" not in frozen
        or (isinstance(additional_specs, list) and bool(additional_specs)),
        "additional frozen evidence rows must be a nonempty list",
    )
    located["additional_evidence"] = [
        _locate_frozen_row(spec, baseline, "evidence", "evidence_id")
        for spec in additional_specs or []
    ]
    project, site, evidence = (
        located[name]["row"] for name in ("projects", "sites", "evidence")
    )
    _require(
        project["project_stable_key"] == project_key
        and site["physical_site_stable_key"] == site_key
        and project["physical_site_stable_key"] == site_key
        and project["site_id"] == site["site_id"],
        "baseline correction project/site rows differ",
    )
    _require(
        site["project_count"] == "1"
        and _json_field(site["project_ids_json"], "frozen site projects")
        == [project["project_id"]]
        and _json_field(site["project_stable_keys_json"], "frozen site project keys")
        == [project_key]
        and sum(
            row["physical_site_stable_key"] == site_key for row in baseline["projects"]
        )
        == 1,
        "baseline corrections support single-project sites only",
    )
    superseded = evidence["evidence_id"]
    superseded_rows = [evidence, *(item["row"] for item in located["additional_evidence"])]
    superseded_ids = [row["evidence_id"] for row in superseded_rows]
    site_evidence = _json_field(site["geometry_evidence_ids_json"], "frozen site evidence")
    _require(
        len(set(superseded_ids)) == len(superseded_ids)
        and project["geometry_evidence_id"] == superseded
        and isinstance(site_evidence, list)
        and len(site_evidence) == len(set(site_evidence)) == len(superseded_ids)
        and set(site_evidence) == set(superseded_ids)
        and all(
            _json_field(row["roles_json"], "frozen evidence roles") == ["geometry"]
            and _json_field(row["project_ids_json"], "frozen evidence projects")
            == [project["project_id"]]
            for row in superseded_rows
        ),
        "superseded evidence row is not solely this project's geometry evidence",
    )
    for table in ("projects", "sites"):
        for index, row in enumerate(baseline[table]):
            _require(
                index == located[table]["index"]
                or not any(
                    identifier in str(value)
                    for identifier in superseded_ids
                    for value in row.values()
                ),
                "superseded evidence row is referenced by another inherited row",
            )
    located["superseded_evidence_ids"] = superseded_ids
    located["feature"] = _locate_frozen_feature(frozen["sites_geojson"], baseline, site)
    return located


def _locate_frozen_feature(
    spec: Any, baseline: Mapping[str, Any], site: Mapping[str, Any]
) -> dict[str, Any]:
    """Hash-check the frozen v0.17 GeoJSON feature of a frozen site row."""
    spec = _keys(
        spec,
        {"feature_index", "feature_canonical_sha256"},
        "frozen GeoJSON feature",
    )
    geojson = _json(baseline["files"]["sites.geojson"], "baseline GeoJSON")
    features = geojson.get("features") if isinstance(geojson, dict) else None
    index = spec["feature_index"]
    _require(
        isinstance(features, list)
        and type(index) is int
        and 0 <= index < len(features),
        "frozen GeoJSON feature index differs",
    )
    feature = features[index]
    _require(
        canonical_sha256(feature)
        == _hash(spec["feature_canonical_sha256"], "frozen feature hash"),
        "frozen GeoJSON feature SHA-256 differs",
    )
    _require(
        feature == core._geojson([site])["features"][0],
        "frozen GeoJSON feature does not reproduce its site row",
    )
    return {"index": index, "feature": feature}


def _withdrawn_frozen_rows(
    frozen: Any, baseline: Mapping[str, Any], project_key: str, site_key: str
) -> dict[str, Any]:
    """Locate and hash-check every frozen v0.17 row and feature a withdrawal removes.

    The project must be the only project of its site, and ``evidence_csv`` must
    list, in file order, exactly the frozen evidence rows whose project
    association names it; each must name it alone. A project on a shared site or
    with a shared evidence row needs a reviewed re-derivation of those rows,
    which a withdrawal never performs, so both fail closed.
    """
    _keys(frozen, FROZEN_ROWS_KEYS, "baseline withdrawal frozen rows")
    _require(
        frozen["release_path"] == BASELINE_RELATIVE_DIR
        and frozen["manifest_sha256"] == BASELINE_MANIFEST_SHA256,
        "baseline withdrawal must name rows of the pinned v0.17 manifest",
    )
    located: dict[str, Any] = {
        "projects": _locate_frozen_row(
            frozen["projects_csv"], baseline, "projects", "project_stable_key"
        ),
        "sites": _locate_frozen_row(
            frozen["sites_csv"], baseline, "sites", "physical_site_stable_key"
        ),
    }
    specs = frozen["evidence_csv"]
    _require(
        isinstance(specs, list) and bool(specs),
        "withdrawn evidence rows must be a nonempty list",
    )
    evidence = [
        _locate_frozen_row(spec, baseline, "evidence", "evidence_id") for spec in specs
    ]
    _require(
        all(first["line"] < second["line"] for first, second in zip(evidence, evidence[1:])),
        "withdrawn evidence rows must be listed once each, in file order",
    )
    project, site = located["projects"]["row"], located["sites"]["row"]
    _require(
        project["project_stable_key"] == project_key
        and site["physical_site_stable_key"] == site_key
        and project["physical_site_stable_key"] == site_key
        and project["site_id"] == site["site_id"],
        "baseline withdrawal project/site rows differ",
    )
    project_id = project["project_id"]
    _require(
        site["project_count"] == "1"
        and _json_field(site["project_ids_json"], "frozen site projects") == [project_id]
        and _json_field(site["project_stable_keys_json"], "frozen site project keys")
        == [project_key]
        and sum(
            row["physical_site_stable_key"] == site_key for row in baseline["projects"]
        )
        == 1,
        "baseline withdrawals support single-project sites only; withdrawing a project "
        "from a shared site needs a reviewed re-derivation of the site row",
    )
    named = [item["row"]["evidence_id"] for item in evidence]
    associated = [
        row["evidence_id"]
        for row in baseline["evidence"]
        if project_id in _json_field(row["project_ids_json"], "frozen evidence projects")
    ]
    _require(
        named == associated,
        "withdrawn evidence rows differ from the frozen evidence rows of the project",
    )
    _require(
        all(
            _json_field(item["row"]["project_ids_json"], "frozen evidence projects")
            == [project_id]
            for item in evidence
        ),
        "withdrawn evidence row is shared with another project; a shared-row "
        "withdrawal needs a reviewed re-derivation of its usage",
    )
    known = {row["evidence_id"] for row in baseline["evidence"]}
    _require(
        {
            identifier
            for identifier in known
            for row in (project, site)
            if any(identifier in str(value) for value in row.values())
        }
        <= set(named),
        "the withdrawn project or site row references evidence that is not withdrawn",
    )
    removed = {project_id, site["site_id"], *named}
    skip = {
        "projects": {located["projects"]["index"]},
        "sites": {located["sites"]["index"]},
        "evidence": {item["index"] for item in evidence},
    }
    for table, indices in skip.items():
        for index, row in enumerate(baseline[table]):
            _require(
                index in indices
                or not any(
                    identifier in str(value)
                    for identifier in removed
                    for value in row.values()
                ),
                "a withdrawn row is referenced by another inherited row",
            )
    located["evidence"] = evidence
    located["evidence_ids"] = named
    located["feature"] = _locate_frozen_feature(frozen["sites_geojson"], baseline, site)
    return located


def _inherited_unchanged_through(
    spec: Any,
    root: Path,
    frozen: Mapping[str, Any],
    formats: frozenset[str] = INHERITED_THROUGH_FORMATS_V2,
) -> dict[str, frozenset[bytes]]:
    """Prove the frozen rows were still byte-identical in the named later draft.

    The release must be a v0.18 draft built on the pinned v0.17 manifest, never
    the frozen baseline itself. Returns that draft's project and site data lines.
    """
    _keys(
        spec,
        {"release_path", "manifest_sha256", "rows_byte_identical_to_v017"},
        "inherited-through release",
    )
    _require(
        spec["rows_byte_identical_to_v017"] is True,
        "inherited-through release must preserve the frozen rows",
    )
    release = spec["release_path"]
    directory = _portable_path(root, release, "inherited-through release path")
    _require(
        Path(release).parts[0] == "verified_construction_core"
        and not directory.is_symlink()
        and directory.is_dir(),
        "inherited-through release is not a release directory",
    )
    _require(
        Path(release).as_posix() != BASELINE_RELATIVE_DIR
        and directory.resolve() != (root / BASELINE_RELATIVE_DIR).resolve()
        and spec["manifest_sha256"] != BASELINE_MANIFEST_SHA256,
        "inherited-through release must be a later v0.18 draft, not the frozen baseline",
    )
    manifest = _json(
        _read_pinned(directory / "manifest.json", spec["manifest_sha256"]),
        "inherited-through manifest",
    )
    _require(
        isinstance(manifest, dict)
        and isinstance(manifest.get("format"), str)
        and manifest["format"] in formats
        and manifest.get("release_status") == "draft"
        and manifest.get("base_preview_manifest_sha256") == BASELINE_MANIFEST_SHA256
        and manifest.get("base_preview_path") == BASELINE_RELATIVE_DIR,
        "inherited-through release is not a v0.18 draft of the pinned v0.17 baseline",
    )
    files = manifest.get("files")
    _require(isinstance(files, dict), "inherited-through manifest lacks files")
    data = {}
    for name in ("projects.csv", "sites.csv", "evidence.csv", "sites.geojson"):
        entry = files.get(name)
        _require(
            isinstance(entry, dict) and type(entry.get("bytes")) is int,
            f"inherited-through manifest lacks {name}",
        )
        data[name] = _read_pinned(directory / name, entry.get("sha256"), entry["bytes"])
    # Rows are located by their frozen raw bytes, not by line number: an earlier
    # correction's dropped evidence row shifts later evidence lines up by one,
    # and only byte identity, not position, is being proven here.
    digests = {
        table: Counter(
            hashlib.sha256(line).hexdigest()
            for line in data[f"{table}.csv"].split(b"\n")[1:]
            if line
        )
        for table in ("projects", "sites", "evidence")
    }
    # A correction names one primary evidence row plus optional additional rows;
    # a withdrawal names its list of removed evidence rows.
    evidence_specs = (
        list(frozen["evidence_csv"])
        if isinstance(frozen["evidence_csv"], list)
        else [frozen["evidence_csv"], *frozen.get("additional_evidence_csv", [])]
    )
    expected = [
        ("projects", frozen["projects_csv"]["raw_line_sha256"]),
        ("sites", frozen["sites_csv"]["raw_line_sha256"]),
    ] + [("evidence", item["raw_line_sha256"]) for item in evidence_specs]
    for table, digest in expected:
        _require(
            digests[table][digest] == 1,
            f"inherited {table} row changed after v0.17",
        )
    # The feature is located by its frozen canonical hash, exactly once, for the
    # same reason: a v3 withdrawal drops a feature and shifts the later ones.
    geojson = _json(data["sites.geojson"], "inherited-through GeoJSON")
    features = geojson.get("features") if isinstance(geojson, dict) else None
    feature_digest = frozen["sites_geojson"]["feature_canonical_sha256"]
    _require(
        isinstance(features, list)
        and sum(canonical_sha256(feature) == feature_digest for feature in features) == 1,
        "inherited GeoJSON feature changed after v0.17",
    )
    return {
        table: frozenset(
            line for line in data[f"{table}.csv"].split(b"\n")[1:] if line
        )
        for table in ("projects", "sites")
    }


def _superseded(
    supersedes: Any,
    root: Path,
    baseline: Mapping[str, Any],
    located: Mapping[str, Any],
    correction: Mapping[str, Any],
    formats: frozenset[str] = INHERITED_THROUGH_FORMATS_V2,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, frozenset[bytes]]]:
    """Bind the frozen rows to the superseded record of the frozen v0.16 facts.

    Returns the superseded evidence record, the additional superseded evidence
    entries (each with its v0.16 record), and the inherited-through draft's
    project and site data lines.
    """
    _require(
        isinstance(supersedes, dict)
        and SUPERSEDES_KEYS <= set(supersedes)
        and set(supersedes) <= SUPERSEDES_KEYS | SUPERSEDES_OPTIONAL_KEYS,
        "baseline correction supersedes keys differ",
    )
    relative = supersedes["source_path"]
    path = _portable_path(root, relative, "superseded source path")
    _require(Path(relative).parts[0] == "sources", "superseded source must be under sources/")
    _require(
        _pinned_v017_input(
            baseline,
            relative,
            supersedes["source_file_sha256"],
            supersedes["source_file_bytes"],
        ),
        "superseded source is not a pinned v0.17 portable input",
    )
    document = _json(
        _read_pinned(
            path, supersedes["source_file_sha256"], supersedes["source_file_bytes"]
        ),
        "superseded source",
    )
    evidence = _pointer(document, supersedes["evidence_pointer"])
    _require(
        isinstance(evidence, dict)
        and canonical_sha256(evidence)
        == _hash(supersedes["evidence_record_sha256"], "superseded evidence hash"),
        "superseded evidence record SHA-256 differs",
    )
    project = located["projects"]["row"]
    site = located["sites"]["row"]
    frozen_evidence = located["evidence"]["row"]
    _require(
        evidence.get("source_id")
        == _text(supersedes["evidence_source_id"], "superseded evidence source")
        and evidence.get("evidence_id")
        == supersedes["evidence_id"]
        == frozen_evidence["evidence_id"],
        "superseded evidence identity differs",
    )
    _require(
        all(
            frozen_evidence[field] == value
            for field, value in core._v07_evidence_projection(evidence).items()
        ),
        "frozen evidence row is not the superseded record",
    )
    record = _pointer(document, supersedes["geometry_pointer"])
    _require(
        isinstance(record, dict)
        and canonical_sha256(record)
        == _hash(supersedes["geometry_record_sha256"], "superseded geometry hash"),
        "superseded geometry record SHA-256 differs",
    )
    _require(
        record.get("locator_id") == _text(supersedes["locator_id"], "superseded locator")
        and record.get("project_stable_key") == correction["project_stable_key"]
        and record.get("geometry_source_document_id")
        == supersedes["evidence_source_id"],
        "superseded geometry identity differs",
    )
    declared = supersedes.get("additional_superseded_evidence", None)
    _require(
        "additional_superseded_evidence" not in supersedes
        or (isinstance(declared, list) and bool(declared)),
        "additional superseded evidence must be a nonempty list",
    )
    declared = declared or []
    frozen_additional = located["additional_evidence"]
    _require(
        len(declared) == len(frozen_additional),
        "additional superseded evidence differs from the additional frozen rows",
    )
    additional = []
    for item, frozen_item in zip(declared, frozen_additional):
        _keys(item, ADDITIONAL_SUPERSEDED_KEYS, "additional superseded evidence")
        value = _pointer(document, item["evidence_pointer"])
        frozen_row = frozen_item["row"]
        _require(
            isinstance(value, dict)
            and canonical_sha256(value)
            == _hash(item["evidence_record_sha256"], "additional superseded evidence hash")
            and value.get("source_id")
            == _text(item["evidence_source_id"], "additional superseded source")
            and value.get("evidence_id")
            == item["evidence_id"]
            == frozen_row["evidence_id"]
            and all(
                frozen_row[field] == cell
                for field, cell in core._v07_evidence_projection(value).items()
            ),
            "additional frozen evidence row is not its superseded record",
        )
        _text(item["replacement_source_id"], "additional replacement source")
        additional.append({**item, "record": value})
    # Every geometry source of the superseded locator must be superseded, and
    # only those: a correction cannot leave part of a frozen locator unbound.
    _require(
        record.get(
            "geometry_source_document_ids", [supersedes["evidence_source_id"]]
        )
        == [supersedes["evidence_source_id"]]
        + [item["evidence_source_id"] for item in additional],
        "superseded evidence does not cover the frozen locator's geometry sources",
    )
    try:
        geometry = core._v15_result_geometry(record)
    except core.VerifiedConstructionCoreError as exc:
        raise DraftValidationError("superseded geometry cannot be decoded") from exc
    _require(
        _json_cell(geometry) == project["geometry_json"] == site["geometry_json"]
        and geometry["type"] == project["geometry_type"] == site["geometry_type"],
        "frozen geometry is not the superseded record",
    )
    anchor = record.get("display_anchor")
    _require(
        isinstance(anchor, dict)
        and anchor.get("coordinates")
        == [float(project["longitude"]), float(project["latitude"])],
        "frozen display anchor is not the superseded record",
    )
    semantics = record.get("semantics")
    _require(
        isinstance(semantics, dict)
        and all(
            project[field] == semantics.get(field)
            for field in sorted(SEMANTIC_FIELDS)
            if field.startswith("geometry_")
        )
        and project["geometry_precision_scope"] == semantics.get("precision_scope")
        and project["horizontal_uncertainty_unknown_reason"]
        == semantics.get("horizontal_uncertainty_unknown_reason")
        and project["horizontal_uncertainty_metres"] == ""
        and semantics.get("horizontal_uncertainty_metres") is None,
        "frozen locator semantics are not the superseded record",
    )
    _require(
        supersedes["frozen_baseline_rows"] == correction["frozen_rows"],
        "contract frozen rows differ from the correction record",
    )
    _text(supersedes["correction_reason"], "superseded correction reason")
    _require(
        supersedes["frozen_artifact_mutated"] is False,
        "a baseline correction cannot mutate a frozen artifact",
    )
    inherited_lines = _inherited_unchanged_through(
        supersedes["inherited_unchanged_through"],
        root,
        correction["frozen_rows"],
        formats,
    )
    return evidence, additional, inherited_lines


def _resolve_binding(
    binding: Any,
    root: Path,
    baseline: Mapping[str, Any],
    *,
    seen: Mapping[str, Any] | frozenset[str] = frozenset(),
    label: str = "unchanged binding",
) -> tuple[str, dict[str, Any]]:
    """Resolve one pinned file binding to its hash-checked records.

    Returns its source ID and ``{"records", "v017_input"}``; ``seen`` holds the
    source IDs already resolved alongside it, which must not repeat.
    """
    _require(isinstance(binding, dict), f"{label} is not an object")
    pairs = [pair for pair in BINDING_POINTERS if pair[0] in binding]
    expected = {"source_id", "source_path", "source_file_sha256", "source_file_bytes"}
    expected.update(key for pair in pairs for key in pair)
    if "note" in binding:
        expected.add("note")
        _text(binding["note"], f"{label} note")
    _keys(binding, expected, label)
    _require(bool(pairs), f"{label} pins no record")
    source_id = _text(binding["source_id"], f"{label} ID")
    _require(source_id not in seen, f"duplicate {label}")
    relative = binding["source_path"]
    path = _portable_path(root, relative, f"{label} path")
    _require(
        Path(relative).parts[0] in {"sources", "definitions"},
        f"{label} must be a sources/ or definitions/ input",
    )
    bound = _json(
        _read_pinned(path, binding["source_file_sha256"], binding["source_file_bytes"]),
        source_id,
    )
    records = {}
    for pointer_key, hash_key in pairs:
        value = _pointer(bound, binding[pointer_key])
        _require(
            isinstance(value, dict)
            and canonical_sha256(value)
            == _hash(binding[hash_key], f"{source_id} {hash_key}"),
            f"{label} record SHA-256 differs: {source_id}",
        )
        records[pointer_key.removesuffix("_pointer")] = value
    return source_id, {
        "records": records,
        "v017_input": _pinned_v017_input(
            baseline,
            relative,
            binding["source_file_sha256"],
            binding["source_file_bytes"],
        ),
    }


def _frozen_status_identity(
    resolved: Mapping[str, Any],
    project: Mapping[str, Any],
    project_key: str,
    site_key: str,
    baseline: Mapping[str, Any],
    source_id: str,
    label: str = "identity binding",
) -> dict[str, Any]:
    """Require a resolved binding to be the frozen v0.17 curated input of a project.

    Its project, campus, lifecycle row and evidence must reproduce the frozen
    project row's identity, lifecycle observation and status evidence row.
    Returns the status evidence projection.
    """
    records = resolved["records"]
    _require(
        resolved["v017_input"]
        and set(records) == {"evidence", "project", "campus", "lifecycle"},
        f"{label} is not a pinned v0.17 curated input",
    )
    _require(
        records["project"].get("stable_key") == project_key
        and records["campus"].get("stable_key") == site_key,
        f"{label} project/campus differs",
    )
    status = records["lifecycle"]
    _require(
        status.get("entity") == "project"
        and status.get("value") == project["last_observed_physical_status"]
        and status.get("as_of_date") == project["status_as_of"]
        and status.get("method") == project["status_method"]
        and status.get("evidence_key") == records["evidence"].get("key"),
        f"frozen lifecycle observation differs from the {label}",
    )
    # A frozen v0.17 curated input may itself carry an inherited date-only
    # retrieval. It is accepted here only because the projection must then equal
    # the frozen status evidence row field for field (checked just below).
    status_evidence = _source_evidence(
        records["evidence"],
        source_id,
        inherited_date_only_retrieval=_date_only(records["evidence"].get("retrieved_at")),
    )
    frozen_status = [
        row
        for row in baseline["evidence"]
        if row["evidence_id"] == status_evidence["evidence_id"]
    ]
    _require(
        status_evidence["evidence_id"] == project["status_evidence_id"]
        and status_evidence["source_url"] == project["status_source_url"]
        and len(frozen_status) == 1
        and all(
            frozen_status[0][field] == value for field, value in status_evidence.items()
        ),
        f"{label} is not the frozen status evidence",
    )
    return status_evidence


def _unchanged_bindings(
    document: Mapping[str, Any],
    root: Path,
    baseline: Mapping[str, Any],
    located: Mapping[str, Any],
    correction: Mapping[str, Any],
    sources: Mapping[str, Any],
) -> None:
    """Check every unchanged binding and the frozen identity/status it preserves."""
    bindings = document.get("required_unchanged_identity_bindings")
    _require(
        isinstance(bindings, list) and bool(bindings),
        "baseline correction lacks unchanged identity bindings",
    )
    resolved: dict[str, dict[str, Any]] = {}
    for binding in bindings:
        source_id, item = _resolve_binding(binding, root, baseline, seen=resolved)
        resolved[source_id] = item
    identity_id = correction["identity_source_id"]
    identity = resolved.get(identity_id)
    _require(
        identity is not None and identity_id not in sources,
        "identity source must be an unchanged frozen binding, not a contract source",
    )
    _frozen_status_identity(
        identity,
        located["projects"]["row"],
        correction["project_stable_key"],
        correction["physical_site_stable_key"],
        baseline,
        identity_id,
    )
    for source_id, item in resolved.items():
        if "acceptance" in item["records"]:
            _require(
                item["v017_input"]
                and item["records"]["acceptance"].get("project_stable_key")
                == correction["project_stable_key"],
                f"unchanged acceptance binding differs: {source_id}",
            )
        if source_id in sources:
            _require(
                "evidence" in item["records"]
                and sources[source_id]["evidence"] == item["records"]["evidence"],
                f"correction evidence differs from its bound original: {source_id}",
            )


def _baseline_correction_geometry(
    record: Any, correction: Mapping[str, Any], located: Mapping[str, Any]
) -> bool:
    """Dedicated correction validator: host-estate context, frozen numbers only.

    Returns whether the display anchor lies inside the geometry. A frozen
    exterior anchor is tolerated here because the numbers must equal the frozen
    row exactly; ``_preservation_invariants`` then requires the record to declare
    it (``display_anchor_outside_geometry``), and never otherwise.
    """
    _geometry_shape(
        record, "baseline correction geometry record", exterior_anchor_allowed=True
    )
    semantics = _keys(
        record["semantics"], SEMANTIC_FIELDS, "baseline correction geometry semantics"
    )
    for field in sorted(
        SEMANTIC_FIELDS
        - {"horizontal_uncertainty_metres", "horizontal_uncertainty_unknown_reason"}
    ):
        _text(semantics[field], f"baseline correction semantics {field}")
    _require(
        isinstance(record["location_basis"], str)
        and record["location_basis"] in BASELINE_CORRECTION_LOCATION_BASES
        and semantics["geometry_source_entity_kind"] in BASELINE_CORRECTION_ENTITY_KINDS
        and semantics["geometry_use_scope"] in BASELINE_CORRECTION_USE_SCOPES,
        "baseline correction must re-scope its locator to host-estate locality context",
    )
    project = located["projects"]["row"]
    site = located["sites"]["row"]
    _require(
        record["project_stable_key"] == correction["project_stable_key"]
        and record["parent_campus_stable_key"] == correction["physical_site_stable_key"],
        "baseline correction geometry identity differs",
    )
    _require(
        semantics["geometry_authority_class"] in {"official_source", "community_source"}
        and semantics["geometry_authority_class"] == project["geometry_authority_class"],
        "baseline correction cannot change geometry authority",
    )
    _require(
        semantics["horizontal_uncertainty_metres"] is None
        and project["horizontal_uncertainty_metres"] == "",
        "host-estate context cannot assert a numeric site uncertainty",
    )
    _text(
        semantics["horizontal_uncertainty_unknown_reason"],
        "baseline correction unknown uncertainty reason",
    )
    geometry = record["geometry"]
    _require(
        _json_cell(geometry) == project["geometry_json"] == site["geometry_json"]
        and geometry["type"] == project["geometry_type"] == site["geometry_type"],
        "baseline correction geometry differs from the frozen row",
    )
    longitude, latitude = record["display_anchor"]["coordinates"]
    _require(
        repr(longitude) == project["longitude"] == site["longitude"]
        and repr(latitude) == project["latitude"] == site["latitude"]
        and [float(project["longitude"]), float(project["latitude"])]
        == [longitude, latitude],
        "baseline correction display anchor differs from the frozen row",
    )
    return _anchor_inside_geometry(record)


def _correction_document(
    document: Any,
    sources: Mapping[str, Any],
    source_id: str,
    reviewed_at: date,
) -> None:
    _require(isinstance(document, dict), "correction record is not an object")
    _require(
        document.get("lifecycle_reference_date") == LIFECYCLE_REFERENCE_DATE.isoformat(),
        "correction lifecycle cutoff cannot move",
    )
    _require(
        type(document.get("accepted_additional_sites")) is int
        and document["accepted_additional_sites"] == 0,
        "a baseline correction cannot add sites",
    )
    corrected_at = _calendar(document.get("reviewed_at"), "correction review date")
    _require(
        LIFECYCLE_REFERENCE_DATE <= corrected_at <= reviewed_at,
        "correction review date falls outside the checkpoint review",
    )
    path = sources[source_id]["spec"]["path"]
    bound = sorted(
        (other_id, source["spec"]["evidence_pointer"])
        for other_id, source in sources.items()
        if source["spec"]["path"] == path
    )
    declared = document.get("source_bindings")
    _require(
        isinstance(declared, list)
        and all(
            isinstance(item, dict)
            and set(item) == {"source_id", "evidence_pointer"}
            and isinstance(item["source_id"], str)
            and isinstance(item["evidence_pointer"], str)
            for item in declared
        )
        and sorted((item["source_id"], item["evidence_pointer"]) for item in declared)
        == bound,
        "correction source bindings differ from the contract sources",
    )


def _same_capture_value(field: str, reused: Any, frozen: Any) -> bool:
    """Literal equality, except one projection-equivalent publication value.

    A frozen v0.16 record may store an unknown publication date as the empty
    string, which the curated evidence shape cannot carry (it requires null or
    nonempty text). Null and the empty string project to the same empty evidence
    cell, so exactly that pair is equal for ``published_at``; nothing else is.
    """
    if field == "published_at" and reused is None and frozen == "":
        return True
    return reused == frozen


def _reused_capture(
    evidence: Mapping[str, Any],
    superseded: Mapping[str, Any],
    supersedes: Mapping[str, Any],
) -> None:
    _require(
        all(
            _same_capture_value(field, evidence.get(field), superseded.get(field))
            for field in CAPTURE_FIELDS
        ),
        "primary correction source is not the reused frozen capture",
    )
    metadata = evidence.get("metadata")
    if isinstance(metadata, dict) and "supersedes" in metadata:
        claimed = metadata["supersedes"]
        _require(
            isinstance(claimed, dict)
            and all(
                key in supersedes and supersedes[key] == value
                for key, value in claimed.items()
            ),
            "reused capture metadata names a different superseded record",
        )


def _osm_version_matches(
    version: Any, superseded: Mapping[str, Any], reused: Mapping[str, Any]
) -> bool:
    facts = superseded.get("facts")
    metadata = reused.get("metadata")
    return (
        type(version) is int
        and isinstance(facts, dict)
        and type(facts.get("version")) is int
        and facts["version"] == version
        and (
            not isinstance(metadata, dict)
            or "osm_version" not in metadata
            or (
                type(metadata["osm_version"]) is int
                and metadata["osm_version"] == version
            )
        )
    )


def _preservation_invariants(
    document: Mapping[str, Any],
    located: Mapping[str, Any],
    record: Mapping[str, Any],
    superseded: Mapping[str, Any],
    reused: Mapping[str, Any],
    additional: Sequence[Mapping[str, Any]] = (),
    anchor_inside: bool = True,
) -> dict[str, Any]:
    """Check every invariant key; unrecognized keys are rejected, not trusted.

    ``osm_way_version_unchanged`` must equal the superseded record's OSM way
    version (and the reused capture's, when its metadata states one).
    ``intersecting_site_rows_unchanged`` lists other site keys; after the
    batch is derived, each must intersect the corrected geometry and keep its
    project and site lines byte for byte from the inherited-through draft.
    ``additional_superseded_captures_unchanged`` is required exactly when the
    correction supersedes additional evidence rows: one entry per row, in order,
    restating its evidence ID, raw-body hash, retrieval value and (optionally)
    OSM way version. ``display_anchor_outside_geometry`` is required, and must be
    true, exactly when the unchanged frozen anchor lies outside its polygons.
    """
    invariants = document.get("preservation_invariants")
    _require(isinstance(invariants, dict), "baseline correction lacks invariants")
    project = located["projects"]["row"]
    expected = {
        "raw_evidence_body_sha256_unchanged": superseded["content_hash"],
        "raw_capture_retrieved_at_unchanged": superseded["retrieved_at"],
        "numeric_geometry_unchanged": True,
        "display_anchor_unchanged": record["display_anchor"]["coordinates"],
        "geometry_authority_class_unchanged": project["geometry_authority_class"],
        "physical_campus_key_unchanged": True,
        "construction_project_key_unchanged": True,
        "lifecycle_observation_unchanged": {
            "value": project["last_observed_physical_status"],
            "as_of_date": project["status_as_of"],
            "method": project["status_method"],
        },
        "horizontal_uncertainty_metres": None,
        "site_count_unchanged": True,
        "old_file_not_modified": True,
        "frozen_v017_not_modified": True,
    }
    for key, value in expected.items():
        _require(
            key in invariants
            and canonical_sha256(invariants[key]) == canonical_sha256(value),
            f"baseline correction preservation invariant differs: {key}",
        )
    unchecked = set(invariants) - set(expected) - OPTIONAL_PRESERVATION_INVARIANTS
    _require(
        not unchecked,
        "baseline correction preservation invariant is not machine-checked: "
        + ", ".join(sorted(unchecked)),
    )
    if "osm_way_version_unchanged" in invariants:
        _require(
            _osm_version_matches(
                invariants["osm_way_version_unchanged"], superseded, reused
            ),
            "baseline correction preservation invariant differs: "
            "osm_way_version_unchanged",
        )
    _require(
        ("additional_superseded_captures_unchanged" in invariants) == bool(additional),
        "baseline correction preservation invariant differs: "
        "additional_superseded_captures_unchanged",
    )
    if additional:
        entries = invariants["additional_superseded_captures_unchanged"]
        _require(
            isinstance(entries, list) and len(entries) == len(additional),
            "baseline correction preservation invariant differs: "
            "additional_superseded_captures_unchanged",
        )
        for entry, item in zip(entries, additional):
            value = item["record"]
            _require(
                isinstance(entry, dict)
                and ADDITIONAL_CAPTURE_INVARIANT_KEYS <= set(entry)
                and set(entry)
                <= ADDITIONAL_CAPTURE_INVARIANT_KEYS | {"osm_way_version_unchanged"}
                and entry["evidence_id"] == item["evidence_id"]
                and entry["raw_evidence_body_sha256_unchanged"] == value["content_hash"]
                and entry["raw_capture_retrieved_at_unchanged"] == value["retrieved_at"]
                and (
                    "osm_way_version_unchanged" not in entry
                    or _osm_version_matches(
                        entry["osm_way_version_unchanged"], value, item["reused"]
                    )
                ),
                "baseline correction preservation invariant differs: "
                "additional_superseded_captures_unchanged",
            )
    _require(
        (
            invariants.get("display_anchor_outside_geometry") is True
            if not anchor_inside
            else "display_anchor_outside_geometry" not in invariants
        ),
        "baseline correction preservation invariant differs: "
        "display_anchor_outside_geometry",
    )
    if "intersecting_site_rows_unchanged" in invariants:
        keys = _unique_text(
            invariants["intersecting_site_rows_unchanged"],
            "intersecting unchanged site keys",
        )
        _require(
            keys == sorted(keys)
            and located["sites"]["row"]["physical_site_stable_key"] not in keys,
            "baseline correction preservation invariant differs: "
            "intersecting_site_rows_unchanged",
        )
    return invariants


def _intersecting_rows_unchanged(
    batch: ValidatedBatch, delta: Mapping[str, list[dict[str, Any]]]
) -> None:
    """Check each declared intersecting site against the inherited-through draft."""
    declared = [
        item
        for item in batch.baseline_corrections
        if "intersecting_site_rows_unchanged" in item["invariants"]
    ]
    if not declared:
        return
    inherited, _, _ = _inherited(batch)
    projects = [*inherited["projects"], *delta["projects"]]
    sites = {
        row["physical_site_stable_key"]: row
        for row in [*inherited["sites"], *delta["sites"]]
    }
    for item in declared:
        corrected = _json_field(item["site"]["geometry_json"], "corrected site geometry")
        through = item["inherited_through_lines"]
        for key in item["invariants"]["intersecting_site_rows_unchanged"]:
            site = sites.get(key)
            _require(
                site is not None
                and _geometries_intersect(
                    corrected, _json_field(site["geometry_json"], "site geometry")
                ),
                f"declared intersecting site does not intersect the correction: {key}",
            )
            rows = [row for row in projects if row["physical_site_stable_key"] == key]
            _require(
                bool(rows)
                and _csv_line(site, TABLE_FIELDS["sites"]) in through["sites"]
                and all(
                    _csv_line(row, TABLE_FIELDS["projects"]) in through["projects"]
                    for row in rows
                ),
                f"intersecting site rows changed after the inherited-through draft: {key}",
            )


def _corrected_rows(
    record: Mapping[str, Any],
    located: Mapping[str, Any],
    sources: Mapping[str, Any],
    primary_source_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Derive the corrected rows exactly as acceptance rows derive locator fields."""
    semantics = record["semantics"]
    primary = sources[primary_source_id]["projection"]
    posture = _verification_posture(
        semantics["geometry_authority_class"], semantics["geometry_use_scope"]
    )
    reason = semantics["horizontal_uncertainty_unknown_reason"]
    project = dict(located["projects"]["row"])
    project.update(
        {
            **{
                field: semantics[field]
                for field in sorted(SEMANTIC_FIELDS)
                if field.startswith("geometry_")
            },
            "geometry_precision_scope": semantics["precision_scope"],
            "horizontal_uncertainty_metres": "",
            "horizontal_uncertainty_unknown_reason": reason,
            "geometry_evidence_id": primary["evidence_id"],
            "verification_posture": posture,
            "geometry_source_url": primary["source_url"],
        }
    )
    site = dict(located["sites"]["row"])
    site.update(
        {
            "geometry_source_entity_kinds_json": _json_cell(
                [semantics["geometry_source_entity_kind"]]
            ),
            "geometry_derivations_json": _json_cell([semantics["geometry_derivation"]]),
            "geometry_methods_json": _json_cell([semantics["geometry_method"]]),
            "geometry_scope_classes_json": _json_cell(
                [semantics["geometry_scope_class"]]
            ),
            "geometry_authority_classes_json": _json_cell(
                [semantics["geometry_authority_class"]]
            ),
            "geometry_use_scopes_json": _json_cell([semantics["geometry_use_scope"]]),
            "geometry_precision_scopes_json": _json_cell([semantics["precision_scope"]]),
            "horizontal_uncertainty_metres": "",
            "horizontal_uncertainty_unknown_reason": reason,
            "geometry_evidence_ids_json": _json_cell(
                sorted(
                    {
                        sources[source_id]["projection"]["evidence_id"]
                        for source_id in record["geometry_source_ids"]
                    }
                )
            ),
            "verification_posture": posture,
        }
    )
    for row, table in ((project, "projects"), (site, "sites")):
        _csv_line(row, TABLE_FIELDS[table])
    return project, site, core._geojson([site])["features"][0]


def _changed(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, list]:
    _require(set(before) == set(after), "corrected row fields differ")
    return {key: [before[key], after[key]] for key in before if before[key] != after[key]}


def _exact_row_deltas(
    document: Mapping[str, Any],
    located: Mapping[str, Any],
    corrected: Mapping[str, Any],
    correction: Mapping[str, Any],
    sources: Mapping[str, Any],
    geometry_ids: list[str],
) -> dict[str, Any]:
    """Require the derived correction to equal the enumerated exact deltas."""
    deltas = document.get("exact_row_deltas")
    _require(isinstance(deltas, dict), "baseline correction lacks exact row deltas")
    count_keys = [key for key in deltas if key.startswith("counts_relative_to_")]
    _require(len(count_keys) == 1, "baseline correction needs one count-effect block")
    _keys(
        deltas,
        {"projects.csv", "sites.csv", "sites.geojson", "evidence.csv", *count_keys},
        "exact row deltas",
    )
    changed_fields = {}
    for name, table in (("projects.csv", "projects"), ("sites.csv", "sites")):
        spec = _keys(
            deltas[name],
            {"file_line_number", "changed", "unchanged_includes"},
            f"{name} exact delta",
        )
        changed = _changed(located[table]["row"], corrected[table])
        _require(
            spec["file_line_number"] == located[table]["line"]
            and spec["changed"] == changed,
            f"{name} correction differs from its enumerated exact delta",
        )
        unchanged = _unique_text(spec["unchanged_includes"], f"{name} unchanged fields")
        _require(
            set(unchanged).issubset(TABLE_FIELDS[table]),
            f"{name} exact delta lists an unchanged field that is not a column",
        )
        _require(
            not set(unchanged).intersection(changed),
            f"{name} exact delta lists a changed field as unchanged",
        )
        changed_fields[name] = sorted(changed)
    spec = _keys(
        deltas["sites.geojson"],
        {"feature_index", "changed_properties", "geometry_unchanged"},
        "sites.geojson exact delta",
    )
    frozen_feature = located["feature"]["feature"]
    feature = corrected["feature"]
    properties = _changed(frozen_feature["properties"], feature["properties"])
    _require(
        {key: value for key, value in frozen_feature.items() if key != "properties"}
        == {key: value for key, value in feature.items() if key != "properties"}
        and spec["feature_index"] == located["feature"]["index"]
        and spec["geometry_unchanged"] is True
        and spec["changed_properties"] == properties,
        "sites.geojson correction differs from its enumerated exact delta",
    )
    changed_fields["sites.geojson"] = sorted(properties)
    evidence = _keys(
        deltas["evidence.csv"],
        {"removed", "added", "association_only"},
        "evidence.csv exact delta",
    )
    frozen_specs = [
        correction["frozen_rows"]["evidence_csv"],
        *correction["frozen_rows"].get("additional_evidence_csv", []),
    ]
    _require(
        evidence["removed"]
        == [
            {
                "evidence_id": frozen["evidence_id"],
                "file_line_number": frozen["file_line_number"],
                "row_canonical_sha256": frozen["row_canonical_sha256"],
            }
            for frozen in frozen_specs
        ],
        "evidence delta must remove exactly the superseded row",
    )
    by_id = {
        sources[source_id]["projection"]["evidence_id"]: sources[source_id]
        for source_id in geometry_ids
    }
    project_id = corrected["projects"]["project_id"]
    added, shared = evidence["added"], evidence["association_only"]
    _require(
        isinstance(added, list) and isinstance(shared, list),
        "evidence delta lists differ",
    )
    for item in added:
        _keys(item, {"evidence_id", "key", "roles", "project_ids"}, "added evidence")
        source = by_id.get(_text(item["evidence_id"], "added evidence ID"))
        _require(
            source is not None
            and item["key"] == source["evidence"]["key"]
            and item["roles"] == ["geometry"]
            and item["project_ids"] == [project_id],
            "added correction evidence differs from its enumerated delta",
        )
    for item in shared:
        _require(isinstance(item, dict), "association-only evidence is not an object")
        expected = {"evidence_id", "key", "changed_field", "after_adds_project_id"}
        if "note" in item:
            expected.add("note")
            _text(item["note"], "association-only evidence note")
        _keys(item, expected, "association-only evidence")
        source = by_id.get(_text(item["evidence_id"], "association-only evidence ID"))
        _require(
            source is not None
            and item["key"] == source["evidence"]["key"]
            and item["changed_field"] == "project_ids_json"
            and item["after_adds_project_id"] == project_id,
            "association-only correction evidence differs from its enumerated delta",
        )
    added_ids = [item["evidence_id"] for item in added]
    shared_ids = [item["evidence_id"] for item in shared]
    _require(
        len(set(added_ids)) == len(added_ids)
        and len(set(shared_ids)) == len(shared_ids)
        and not set(added_ids).intersection(shared_ids)
        and set(added_ids) | set(shared_ids) == set(by_id),
        "evidence delta does not cover exactly the correction evidence",
    )
    before, after = located["projects"]["row"], corrected["projects"]
    effect = {
        "physical_sites": 0,
        "projects": 0,
        "evidence": len(added) - len(evidence["removed"]),
        "reviewed_site_locator_projects": int(_is_reviewed_locator(after))
        - int(_is_reviewed_locator(before)),
        "host_estate_context_projects": int(_is_host_estate_context(after))
        - int(_is_host_estate_context(before)),
        "official_boundary_projects": int(core._is_official_boundary(after))
        - int(core._is_official_boundary(before)),
        "countries": 0,
        "non_us_sites": 0,
    }
    counts = _keys(deltas[count_keys[0]], CORRECTION_COUNT_KEYS, "correction count effect")
    _require(
        canonical_sha256(counts) == canonical_sha256(effect),
        "baseline correction count effect differs from its enumerated delta",
    )
    return {"changed_fields": changed_fields, "evidence": evidence, "effect": effect}


def _baseline_correction(
    entry: Any,
    root: Path,
    baseline: Mapping[str, Any],
    sources: Mapping[str, Any],
    review_pins: ReviewPins,
    reviewed_at: date,
    formats: frozenset[str] = INHERITED_THROUGH_FORMATS_V2,
) -> dict[str, Any]:
    """Validate one v2 baseline correction fail-closed and derive its rows."""
    _keys(entry, BASELINE_CORRECTION_KEYS, "baseline correction")
    correction_id = _text(entry["correction_id"], "correction ID")
    _require(
        re.fullmatch(r"[a-z0-9][a-z0-9-]{0,95}", correction_id) is not None,
        "unsafe correction ID",
    )
    _require(
        canonical_sha256(entry)
        == review_pins.baseline_correction_sha256.get(correction_id),
        f"independent baseline correction review pin differs: {correction_id}",
    )
    project_key = _text(entry["project_stable_key"], "corrected project key")
    site_key = _text(entry["physical_site_stable_key"], "corrected site key")
    _text(entry["reason"], "baseline correction reason")
    identity_id = _text(entry["identity_source_id"], "correction identity source")
    located = _frozen_rows(entry["frozen_rows"], baseline, project_key, site_key)
    binding = _keys(
        entry["geometry"],
        {"source_id", "record_pointer", "record_sha256"},
        "baseline correction geometry binding",
    )
    source_id = _text(binding["source_id"], "correction geometry source")
    record = _record(
        sources,
        source_id,
        binding["record_pointer"],
        binding["record_sha256"],
        "baseline correction geometry",
    )
    anchor_inside = _baseline_correction_geometry(record, entry, located)
    _require(
        _unique_text(record["identity_source_ids"], "correction identity source IDs")
        == [identity_id],
        "baseline correction identity binding differs",
    )
    geometry_ids = _unique_text(
        record["geometry_source_ids"], "correction geometry source IDs"
    )
    evidence_ids = _unique_text(entry["evidence_source_ids"], "correction evidence IDs")
    _require(
        source_id in geometry_ids
        and set(evidence_ids) == set(geometry_ids)
        and set(geometry_ids).issubset(sources),
        "baseline correction evidence sources differ from its geometry sources",
    )
    document = sources[source_id]["document"]
    _correction_document(document, sources, source_id, reviewed_at)
    supersedes = document.get("supersedes")
    superseded, additional, inherited_lines = _superseded(
        supersedes, root, baseline, located, entry, formats
    )
    reused = sources[source_id]["evidence"]
    _reused_capture(reused, superseded, supersedes)
    # Each additional superseded row is replaced by its own reused capture: a
    # distinct geometry source of this correction with the same capture fields.
    replacements = [item["replacement_source_id"] for item in additional]
    _require(
        len(set(replacements)) == len(replacements)
        and source_id not in replacements
        and set(replacements).issubset(geometry_ids),
        "additional superseded evidence needs distinct replacement geometry sources",
    )
    shared_claim = {
        key: supersedes[key]
        for key in (
            "source_path",
            "source_file_sha256",
            "geometry_pointer",
            "geometry_record_sha256",
            "frozen_artifact_mutated",
        )
    }
    for item in additional:
        replacement = sources[item["replacement_source_id"]]["evidence"]
        _reused_capture(
            replacement,
            item["record"],
            {
                **shared_claim,
                **{
                    key: item[key]
                    for key in (
                        "evidence_pointer",
                        "evidence_record_sha256",
                        "evidence_source_id",
                        "evidence_id",
                    )
                },
            },
        )
        item["reused"] = replacement
    _unchanged_bindings(document, root, baseline, located, entry, sources)
    invariants = _preservation_invariants(
        document, located, record, superseded, reused, additional, anchor_inside
    )
    project, site, feature = _corrected_rows(record, located, sources, source_id)
    corrected = {"projects": project, "sites": site, "feature": feature}
    deltas = _exact_row_deltas(document, located, corrected, entry, sources, geometry_ids)
    return {
        "entry": entry,
        "correction_id": correction_id,
        "located": located,
        "record": record,
        "supersedes": supersedes,
        "primary_source_id": source_id,
        "reused_source_ids": [source_id, *replacements],
        "superseded_evidence_ids": located["superseded_evidence_ids"],
        "geometry_source_ids": geometry_ids,
        "project": project,
        "site": site,
        "feature": feature,
        "changed_fields": deltas["changed_fields"],
        "evidence_delta": deltas["evidence"],
        "count_effect": deltas["effect"],
        "invariants": invariants,
        "inherited_through_lines": inherited_lines,
    }


def _baseline_corrections(
    entries: Any,
    root: Path,
    baseline: Mapping[str, Any],
    sources: Mapping[str, Any],
    review_pins: ReviewPins,
    reviewed_at: date,
    acceptance_sources: set[str],
    date_only_sources: set[str],
    *,
    allow_empty: bool = False,
    formats: frozenset[str] = INHERITED_THROUGH_FORMATS_V2,
) -> list[dict[str, Any]]:
    if allow_empty:
        # Schema v3 carries the key even when it corrects nothing.
        _require(isinstance(entries, list), "v3 baseline corrections must be a list")
    _require(
        isinstance(entries, list) and (allow_empty or bool(entries)),
        "v2 contracts need at least one baseline correction",
    )
    validated = []
    for entry in entries:
        item = _baseline_correction(
            entry, root, baseline, sources, review_pins, reviewed_at, formats
        )
        _require(
            all(
                item[key] != other[key]
                for other in validated
                for key in ("correction_id", "primary_source_id")
            )
            and all(
                item["entry"][key] != other["entry"][key]
                for other in validated
                for key in ("project_stable_key", "physical_site_stable_key")
            ),
            "duplicate baseline correction target",
        )
        validated.append(item)
    _require(
        set(review_pins.baseline_correction_sha256)
        == {item["correction_id"] for item in validated},
        "baseline correction review pin inventory differs",
    )
    reused_lists = [item["reused_source_ids"] for item in validated]
    reused = {source_id for ids in reused_lists for source_id in ids}
    superseded_ids = [
        identifier for item in validated for identifier in item["superseded_evidence_ids"]
    ]
    _require(
        len(reused) == sum(len(ids) for ids in reused_lists)
        and len(set(superseded_ids)) == len(superseded_ids),
        "duplicate baseline correction target",
    )
    for source_id in date_only_sources:
        _require(
            source_id in reused and source_id not in acceptance_sources,
            "date-only retrieval is accepted only for a baseline correction's "
            "reused frozen capture",
        )
    return validated


def _shared_capture_rows(
    evidence: Sequence[Mapping[str, str]],
    projects: Sequence[Mapping[str, str]],
    withdrawn: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    """Evidence rows, other than ``withdrawn``, sharing a withdrawn row's source capture.

    A source capture is the same source URL and content hash, that is the same
    source bytes. Rows keep the order of ``evidence``; each names its projects'
    stable keys and the first withdrawn row (in the given order) it shares with.
    """
    captures: dict[tuple[str, str], str] = {}
    for row in withdrawn:
        captures.setdefault((row["source_url"], row["content_hash"]), row["evidence_id"])
    removed = {row["evidence_id"] for row in withdrawn}
    keys = {row["project_id"]: row["project_stable_key"] for row in projects}
    shared = []
    for row in evidence:
        match = captures.get((row["source_url"], row["content_hash"]))
        if match is None or row["evidence_id"] in removed:
            continue
        project_ids = _json_field(row["project_ids_json"], "shared-capture evidence projects")
        _require(
            isinstance(project_ids, list) and set(project_ids) <= set(keys),
            "a shared-capture evidence row names an unknown project",
        )
        shared.append(
            {
                "evidence_id": row["evidence_id"],
                "project_stable_keys": sorted(keys[project_id] for project_id in project_ids),
                "withdrawn_evidence_id": match,
            }
        )
    return shared


def _shared_capture_gate(
    withdrawals: Sequence[Mapping[str, Any]],
    projects: Sequence[Mapping[str, str]],
    evidence: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """The final-release gate over selected rows sharing a withdrawn source capture.

    A withdrawal neither changes nor re-reviews such rows, so their projects stay
    selected unchanged and the gate stays open while any remains in this checkpoint.
    """
    owners = {
        spec["row"]["evidence_id"]: item["withdrawal_id"]
        for item in withdrawals
        for spec in item["located"]["evidence"]
    }
    rows = _shared_capture_rows(
        evidence,
        projects,
        [spec["row"] for item in withdrawals for spec in item["located"]["evidence"]],
    )
    for row in rows:
        row["withdrawal_id"] = owners[row["withdrawn_evidence_id"]]
    affected = sorted({key for row in rows for key in row["project_stable_keys"]})
    return {
        "actual": len(affected),
        "required": 0,
        "passed": not affected,
        "projects": affected,
        "evidence_rows": rows,
        "reason": "selected projects whose evidence rows share a source capture (the same source URL and content hash) with an evidence row of a withdrawn project; a withdrawal neither changes nor re-reviews them, so each needs its own versioned review before a final release",
    }


def _withdrawal_effect(located: Mapping[str, Any]) -> dict[str, int]:
    """The checkpoint-independent count effect of removing the located rows."""
    project, site = located["projects"]["row"], located["sites"]["row"]
    return {
        "physical_sites": -1,
        "projects": -1,
        "evidence": -len(located["evidence"]),
        "non_us_sites": -int(site["country_iso_a2"] != "US"),
        "reviewed_site_locator_projects": -int(_is_reviewed_locator(project)),
        "host_estate_context_projects": -int(_is_host_estate_context(project)),
        "official_boundary_projects": -int(core._is_official_boundary(project)),
    }


def _baseline_withdrawal(
    entry: Any,
    root: Path,
    baseline: Mapping[str, Any],
    review_pins: ReviewPins,
    reviewed_at: date,
) -> dict[str, Any]:
    """Validate one v3 baseline withdrawal and its pinned record fail-closed."""
    _keys(entry, BASELINE_WITHDRAWAL_KEYS, "baseline withdrawal")
    withdrawal_id = _text(entry["withdrawal_id"], "withdrawal ID")
    _require(
        re.fullmatch(r"[a-z0-9][a-z0-9-]{0,95}", withdrawal_id) is not None,
        "unsafe withdrawal ID",
    )
    _require(
        canonical_sha256(entry)
        == review_pins.baseline_withdrawal_sha256.get(withdrawal_id),
        f"independent baseline withdrawal review pin differs: {withdrawal_id}",
    )
    project_key = _text(entry["project_stable_key"], "withdrawn project key")
    site_key = _text(entry["physical_site_stable_key"], "withdrawn site key")
    _text(entry["reason"], "baseline withdrawal reason")
    located = _withdrawn_frozen_rows(entry["frozen_rows"], baseline, project_key, site_key)
    record_pin = entry["record"]
    document = _json(
        _pinned_review_file(root, record_pin, "sources", "baseline withdrawal record"),
        "baseline withdrawal record",
    )
    _keys(document, BASELINE_WITHDRAWAL_RECORD_KEYS, "baseline withdrawal record")
    _require(
        document["schema_version"] == BASELINE_WITHDRAWAL_RECORD_SCHEMA,
        "baseline withdrawal record schema differs",
    )
    _require(
        document["withdrawal_id"] == withdrawal_id
        and document["project_stable_key"] == project_key
        and document["physical_site_stable_key"] == site_key,
        "baseline withdrawal record names a different withdrawal",
    )
    _require(
        document["lifecycle_reference_date"] == LIFECYCLE_REFERENCE_DATE.isoformat(),
        "withdrawal lifecycle cutoff cannot move",
    )
    _require(
        type(document["accepted_additional_sites"]) is int
        and document["accepted_additional_sites"] == 0,
        "a baseline withdrawal cannot add sites",
    )
    withdrawn_at = _calendar(document["reviewed_at"], "withdrawal review date")
    _require(
        LIFECYCLE_REFERENCE_DATE <= withdrawn_at <= reviewed_at,
        "withdrawal review date falls outside the checkpoint review",
    )
    _require(
        document["decision"] == BASELINE_WITHDRAWAL_DECISION,
        "baseline withdrawal decision differs",
    )
    basis = _choice(
        document["withdrawal_basis"], BASELINE_WITHDRAWAL_BASES, "baseline withdrawal basis"
    )
    boundary = _keys(
        document["claim_boundary"],
        {*BASELINE_WITHDRAWAL_CLAIM_BOUNDARY, "statement"},
        "baseline withdrawal claim boundary",
    )
    _require(
        canonical_sha256({key: boundary[key] for key in BASELINE_WITHDRAWAL_CLAIM_BOUNDARY})
        == canonical_sha256(dict(BASELINE_WITHDRAWAL_CLAIM_BOUNDARY)),
        "a baseline withdrawal asserts no physical status: it cannot claim the project "
        "is paused, cancelled, completed or not under construction",
    )
    _text(boundary["statement"], "baseline withdrawal claim boundary statement")
    _require(
        canonical_sha256(document["frozen_baseline_rows"])
        == canonical_sha256(entry["frozen_rows"]),
        "contract frozen rows differ from the withdrawal record",
    )
    # The withdrawn rows must still be byte-identical in a named later draft, so
    # the rows removed are exactly the rows that draft published.
    _inherited_unchanged_through(
        document["inherited_unchanged_through"],
        root,
        entry["frozen_rows"],
        INHERITED_THROUGH_FORMATS_V3,
    )
    source_id, observation = _resolve_binding(
        document["withdrawn_observation_binding"],
        root,
        baseline,
        label="withdrawn observation binding",
    )
    status_evidence = _frozen_status_identity(
        observation,
        located["projects"]["row"],
        project_key,
        site_key,
        baseline,
        source_id,
        "withdrawn observation binding",
    )
    _require(
        status_evidence["evidence_id"] in located["evidence_ids"],
        "withdrawn observation binding is not a withdrawn evidence row",
    )
    basis_pins = document["review_basis"]
    _require(
        isinstance(basis_pins, list) and bool(basis_pins),
        "baseline withdrawal needs a pinned review basis",
    )
    review_basis = []
    for pin in basis_pins:
        _pinned_review_file(root, pin, "sources", "baseline withdrawal review basis")
        review_basis.append({field: pin[field] for field in ("path", "bytes", "sha256")})
    paths = [pin["path"] for pin in review_basis]
    _require(
        len(set(paths)) == len(paths) and record_pin["path"] not in paths,
        "baseline withdrawal review basis repeats a file or names the record itself",
    )
    effect = _withdrawal_effect(located)
    counts = _keys(document["count_effect"], WITHDRAWAL_COUNT_KEYS, "withdrawal count effect")
    _require(
        canonical_sha256(counts) == canonical_sha256(effect),
        "baseline withdrawal count effect differs from the frozen rows it removes",
    )
    # The record must acknowledge, exactly, every other frozen evidence row that
    # rests on a withdrawn row's source capture; the withdrawal leaves them as they are.
    shared = _keys(
        document["shared_capture_rows"],
        SHARED_CAPTURE_KEYS,
        "baseline withdrawal shared-capture rows",
    )
    _require(
        isinstance(shared["rows"], list)
        and canonical_sha256(shared["rows"])
        == canonical_sha256(
            _shared_capture_rows(
                baseline["evidence"],
                baseline["projects"],
                [item["row"] for item in located["evidence"]],
            )
        ),
        "baseline withdrawal shared-capture rows differ from the frozen evidence rows "
        "that share a withdrawn row's source capture",
    )
    _text(shared["statement"], "baseline withdrawal shared-capture statement")
    _text(document["withdrawal_reason"], "baseline withdrawal record reason")
    return {
        "entry": entry,
        "withdrawal_id": withdrawal_id,
        "located": located,
        "document": document,
        "record_pin": {field: record_pin[field] for field in ("path", "bytes", "sha256")},
        "basis": basis,
        "review_basis": review_basis,
        "observation_source_id": source_id,
        "count_effect": effect,
    }


def _baseline_withdrawals(
    entries: Any,
    root: Path,
    baseline: Mapping[str, Any],
    review_pins: ReviewPins,
    reviewed_at: date,
    corrections: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate every v3 baseline withdrawal; none may touch a corrected row."""
    _require(
        isinstance(entries, list) and bool(entries),
        "v3 baseline withdrawals must be a nonempty list when present",
    )
    validated: list[dict[str, Any]] = []
    for entry in entries:
        item = _baseline_withdrawal(entry, root, baseline, review_pins, reviewed_at)
        _require(
            all(
                item["withdrawal_id"] != other["withdrawal_id"]
                and item["entry"]["record"]["path"] != other["entry"]["record"]["path"]
                and all(
                    item["entry"][key] != other["entry"][key]
                    for key in ("project_stable_key", "physical_site_stable_key")
                )
                for other in validated
            ),
            "duplicate baseline withdrawal target",
        )
        validated.append(item)
    _require(
        set(review_pins.baseline_withdrawal_sha256)
        == {item["withdrawal_id"] for item in validated},
        "baseline withdrawal review pin inventory differs",
    )
    corrected = {
        correction["entry"][key]
        for correction in corrections
        for key in ("project_stable_key", "physical_site_stable_key")
    }
    intersecting = {
        key
        for correction in corrections
        for key in correction["invariants"].get("intersecting_site_rows_unchanged", [])
    }
    for item in validated:
        _require(
            item["entry"]["project_stable_key"] not in corrected
            and item["entry"]["physical_site_stable_key"] not in corrected,
            "a baseline project cannot be both corrected and withdrawn",
        )
        _require(
            item["entry"]["physical_site_stable_key"] not in intersecting,
            "a withdrawn site cannot be a correction's intersecting unchanged site",
        )
    return validated


def _withdrawal_report(withdrawal: Mapping[str, Any]) -> dict[str, Any]:
    entry, document = withdrawal["entry"], withdrawal["document"]
    located = withdrawal["located"]
    project, site = located["projects"]["row"], located["sites"]["row"]
    return {
        "withdrawal_id": withdrawal["withdrawal_id"],
        "physical_site_stable_key": entry["physical_site_stable_key"],
        "project_stable_key": entry["project_stable_key"],
        "site_id": site["site_id"],
        "project_id": project["project_id"],
        "country": site["country"],
        "country_iso_a2": site["country_iso_a2"],
        "withdrawal_record": withdrawal["record_pin"],
        "record_reviewed_at": document["reviewed_at"],
        "decision": document["decision"],
        "withdrawal_basis": withdrawal["basis"],
        "claim_boundary": document["claim_boundary"],
        # The observation the selection relied on; it no longer qualifies, and no
        # other status is asserted in its place.
        "withdrawn_selected_observation": {
            "last_observed_physical_status": project["last_observed_physical_status"],
            "status_as_of": project["status_as_of"],
            "status_method": project["status_method"],
            "status_evidence_id": project["status_evidence_id"],
            "observation_binding_source_id": withdrawal["observation_source_id"],
            "qualifies_for_selection": False,
        },
        "frozen_rows": entry["frozen_rows"],
        "inherited_unchanged_through": document["inherited_unchanged_through"],
        "removed_rows": {
            "projects": [project["project_id"]],
            "sites": [site["site_id"]],
            "evidence": list(located["evidence_ids"]),
            "sites_geojson_frozen_feature_indices": [located["feature"]["index"]],
        },
        "review_basis": withdrawal["review_basis"],
        "count_effect": withdrawal["count_effect"],
        # Other frozen rows on a withdrawn row's source capture, as the record
        # acknowledges them; the withdrawal_shared_capture_review gate tracks those
        # still selected in this checkpoint.
        "shared_capture_rows": document["shared_capture_rows"],
        "additional_sites": 0,
        "reason": entry["reason"],
    }


def _withdrawals_summary(
    withdrawals: Sequence[Mapping[str, Any]], sites: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """The selection report's baseline_withdrawals block for this checkpoint.

    Each withdrawal's count effect is checkpoint-independent; the combined
    effect adds the countries left without any selected site in this checkpoint.
    """
    remaining = {row["country"] for row in sites}
    removed = {item["located"]["sites"]["row"]["country"] for item in withdrawals}
    effect = {
        key: sum(item["count_effect"][key] for item in withdrawals)
        for key in sorted(WITHDRAWAL_COUNT_KEYS)
    }
    effect["countries"] = -len(removed - remaining)
    return {
        "scope": "Inherited v0.17 projects removed from the selection by a pinned schema-v3 baseline withdrawal, because their selected evidence does not meet the acceptance contract. A withdrawal removes the project row, its single-project site row and GeoJSON feature, and every evidence row only it referenced; every other inherited byte is unchanged. It asserts no physical status: a withdrawn project is not claimed to be paused, cancelled, completed or not under construction, and its physical status on the lifecycle reference date is unknown. It neither changes nor re-reviews other rows: selected rows that share a withdrawn row's source capture (the same source URL and content hash) stay selected unchanged, are acknowledged in each record's shared_capture_rows, and keep the withdrawal_shared_capture_review gate open. ATTRIBUTION.txt keeps every inherited v0.17 notice, including notices for sources that only withdrawn rows used. A site-count claim must disclose withdrawals.",
        "withdrawn_projects": len(withdrawals),
        "count_effect": effect,
        "countries_without_selected_site": sorted(removed - remaining),
        "withdrawals": [_withdrawal_report(item) for item in withdrawals],
    }


def _geometry_positions(geometry: Mapping[str, Any]) -> list[list[float]]:
    kind, coordinates = geometry["type"], geometry["coordinates"]
    if kind == "Point":
        return [coordinates]
    polygons = [coordinates] if kind == "Polygon" else coordinates
    return [point for polygon in polygons for ring in polygon for point in ring]


def _geometry_polygons(geometry: Mapping[str, Any]) -> list[list[list[list[float]]]]:
    kind, coordinates = geometry["type"], geometry["coordinates"]
    if kind == "Point":
        return []
    return [coordinates] if kind == "Polygon" else coordinates


def _on_ring(point: list[float], ring: list[list[float]]) -> bool:
    x, y = point
    return any(
        abs((x - ax) * (by - ay) - (y - ay) * (bx - ax)) < 1e-12
        and min(ax, bx) <= x <= max(ax, bx)
        and min(ay, by) <= y <= max(ay, by)
        for (ax, ay), (bx, by) in zip(ring, ring[1:])
    )


def _covers(polygons: list, point: list[float]) -> bool:
    return any(
        _inside_ring(point, polygon[0])
        and not any(
            _inside_ring(point, hole) and not _on_ring(point, hole)
            for hole in polygon[1:]
        )
        for polygon in polygons
    )


def _geometries_intersect(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    """Closed-set intersection of two validated Point/Polygon/MultiPolygon values."""
    boxes = []
    for geometry in (first, second):
        points = _geometry_positions(geometry)
        boxes.append(
            (
                min(point[0] for point in points),
                min(point[1] for point in points),
                max(point[0] for point in points),
                max(point[1] for point in points),
            )
        )
    (ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1) = boxes
    if ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0:
        return False
    first_polygons, second_polygons = (
        _geometry_polygons(first),
        _geometry_polygons(second),
    )
    if not first_polygons and not second_polygons:
        return first["coordinates"] == second["coordinates"]
    if not first_polygons:
        return _covers(second_polygons, first["coordinates"])
    if not second_polygons:
        return _covers(first_polygons, second["coordinates"])

    def edges(polygons: list, box: tuple) -> list:
        x0, y0, x1, y1 = box
        return [
            (a, b)
            for polygon in polygons
            for ring in polygon
            for a, b in zip(ring, ring[1:])
            if max(a[0], b[0]) >= x0
            and min(a[0], b[0]) <= x1
            and max(a[1], b[1]) >= y0
            and min(a[1], b[1]) <= y1
        ]

    if any(
        _segments_intersect(a, b, c, d)
        for a, b in edges(first_polygons, boxes[1])
        for c, d in edges(second_polygons, boxes[0])
    ):
        return True
    return any(_covers(first_polygons, polygon[0][0]) for polygon in second_polygons) or any(
        _covers(second_polygons, polygon[0][0]) for polygon in first_polygons
    )


def _locator_exceptions(
    projects: list[dict[str, Any]],
    sites: list[dict[str, Any]],
    corrections: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    by_project = {item["entry"]["project_stable_key"]: item for item in corrections}
    geometries = {
        row["physical_site_stable_key"]: _json_field(row["geometry_json"], "site geometry")
        for row in sites
    }
    rows = []
    for project in projects:
        if not _is_host_estate_context(project):
            continue
        correction = by_project.get(project["project_stable_key"])
        _require(
            correction is not None,
            "host-estate context requires a pinned baseline correction",
        )
        site_key = project["physical_site_stable_key"]
        rows.append(
            {
                "project_stable_key": project["project_stable_key"],
                "project_id": project["project_id"],
                "physical_site_stable_key": site_key,
                "site_id": project["site_id"],
                "correction_id": correction["correction_id"],
                "geometry_use_scope": project["geometry_use_scope"],
                "verification_posture": project["verification_posture"],
                "counted_as_physical_site": True,
                "counted_as_reviewed_site_locator": False,
                "counted_as_official_boundary": False,
                "display_anchor_is_site_position": False,
                "geometry_intersects_site_keys": sorted(
                    key
                    for key, other in geometries.items()
                    if key != site_key
                    and _geometries_intersect(geometries[site_key], other)
                ),
            }
        )
    return {
        "scope": "Counted projects whose inherited geometry is host-estate locality context only, set by a pinned baseline correction. They are excluded from reviewed_site_locator_projects and official_boundary_projects; the display anchor is not a site position, and other selected sites may lie inside the host estate. A site-count claim must disclose them.",
        "host_estate_context_projects": len(rows),
        "projects": rows,
    }


def _correction_report(
    correction: Mapping[str, Any], batch: ValidatedBatch
) -> dict[str, Any]:
    entry = correction["entry"]
    spec = batch.sources[correction["primary_source_id"]]["spec"]
    supersedes = correction["supersedes"]
    delta = correction["evidence_delta"]
    superseded_record = {
        "source_path": supersedes["source_path"],
        "source_file_sha256": supersedes["source_file_sha256"],
        "evidence_id": supersedes["evidence_id"],
        "locator_id": supersedes["locator_id"],
    }
    if "additional_superseded_evidence" in supersedes:
        # Added only when present, so single-capture reports keep their bytes.
        superseded_record["additional_evidence_ids"] = [
            item["evidence_id"] for item in supersedes["additional_superseded_evidence"]
        ]
    return {
        "correction_id": correction["correction_id"],
        "physical_site_stable_key": entry["physical_site_stable_key"],
        "project_stable_key": entry["project_stable_key"],
        "site_id": correction["site"]["site_id"],
        "project_id": correction["project"]["project_id"],
        "correction_record": {
            "source_id": correction["primary_source_id"],
            "path": spec["path"],
            "sha256": spec["sha256"],
            "record_pointer": entry["geometry"]["record_pointer"],
            "record_sha256": entry["geometry"]["record_sha256"],
        },
        "superseded_record": superseded_record,
        "frozen_rows": entry["frozen_rows"],
        "changed_fields": correction["changed_fields"],
        "evidence_rows": {
            "removed": [item["evidence_id"] for item in delta["removed"]],
            "added": sorted(item["evidence_id"] for item in delta["added"]),
            "association_only": sorted(
                item["evidence_id"] for item in delta["association_only"]
            ),
        },
        "count_effect": correction["count_effect"],
        "unchanged": [
            "physical_site",
            "project",
            "geometry",
            "display_anchor",
            "geometry_authority",
            "lifecycle_observation",
            "status_evidence",
        ],
        "additional_sites": 0,
        "reason": entry["reason"],
    }


# Schema v3: the pinned, pre-registered blind review ------------------------


def _wgs84_distance_m(first: Sequence[float], second: Sequence[float]) -> float:
    """WGS84 ellipsoidal geodesic distance in metres between [lon, lat] points.

    Vincenty's inverse formula, iterated until the longitude change is at most
    1e-12 rad (sub-millimetre). A nearly antipodal pair, for which it may not
    converge, falls back to the great circle on the mean-radius sphere; such a
    pair is thousands of kilometres beyond every agreement threshold.
    """
    lon1, lat1 = float(first[0]), float(first[1])
    lon2, lat2 = float(second[0]), float(second[1])
    if lon1 == lon2 and lat1 == lat2:
        return 0.0
    f = WGS84_F
    longitude = math.radians(lon2 - lon1)
    u1 = math.atan((1 - f) * math.tan(math.radians(lat1)))
    u2 = math.atan((1 - f) * math.tan(math.radians(lat2)))
    sin_u1, cos_u1 = math.sin(u1), math.cos(u1)
    sin_u2, cos_u2 = math.sin(u2), math.cos(u2)
    lam = longitude
    for _ in range(200):
        sin_lam, cos_lam = math.sin(lam), math.cos(lam)
        sin_sigma = math.hypot(
            cos_u2 * sin_lam, cos_u1 * sin_u2 - sin_u1 * cos_u2 * cos_lam
        )
        if sin_sigma == 0:
            return 0.0
        cos_sigma = sin_u1 * sin_u2 + cos_u1 * cos_u2 * cos_lam
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = cos_u1 * cos_u2 * sin_lam / sin_sigma
        cos2_alpha = 1 - sin_alpha * sin_alpha
        cos_2sm = cos_sigma - 2 * sin_u1 * sin_u2 / cos2_alpha if cos2_alpha else 0.0
        c = f / 16 * cos2_alpha * (4 + f * (4 - 3 * cos2_alpha))
        previous = lam
        lam = longitude + (1 - c) * f * sin_alpha * (
            sigma
            + c * sin_sigma * (cos_2sm + c * cos_sigma * (-1 + 2 * cos_2sm * cos_2sm))
        )
        if abs(lam - previous) <= 1e-12:
            break
    else:
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        haversine = (
            math.sin((phi2 - phi1) / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(longitude / 2) ** 2
        )
        return 2 * WGS84_MEAN_RADIUS * math.asin(min(1.0, math.sqrt(haversine)))
    u_sq = cos2_alpha * (WGS84_A**2 - WGS84_B**2) / WGS84_B**2
    big_a = 1 + u_sq / 16384 * (4096 + u_sq * (-768 + u_sq * (320 - 175 * u_sq)))
    big_b = u_sq / 1024 * (256 + u_sq * (-128 + u_sq * (74 - 47 * u_sq)))
    delta = big_b * sin_sigma * (
        cos_2sm
        + big_b
        / 4
        * (
            cos_sigma * (-1 + 2 * cos_2sm * cos_2sm)
            - big_b
            / 6
            * cos_2sm
            * (-3 + 4 * sin_sigma * sin_sigma)
            * (-3 + 4 * cos_2sm * cos_2sm)
        )
    )
    return WGS84_B * big_a * (sigma - delta)


def _wgs84_edge_distance_m(
    point: Sequence[float], start: Sequence[float], end: Sequence[float]
) -> float:
    """Minimum WGS84 distance from ``point`` to a longitude/latitude-straight edge.

    The distance along a site-scale edge is unimodal in the edge parameter, so a
    golden-section search, with both endpoints also checked, finds the minimum
    to far below a millimetre.
    """

    def at(fraction: float) -> float:
        return _wgs84_distance_m(
            point,
            (
                start[0] + fraction * (end[0] - start[0]),
                start[1] + fraction * (end[1] - start[1]),
            ),
        )

    ratio = (math.sqrt(5) - 1) / 2
    low, high = 0.0, 1.0
    left, right = high - ratio * (high - low), low + ratio * (high - low)
    left_value, right_value = at(left), at(right)
    for _ in range(64):
        if left_value <= right_value:
            high, right, right_value = right, left, left_value
            left = high - ratio * (high - low)
            left_value = at(left)
        else:
            low, left, left_value = left, right, right_value
            right = low + ratio * (high - low)
            right_value = at(right)
    return min(at(0.0), at(1.0), left_value, right_value)


def _edge_length_bound_m(start: Sequence[float], end: Sequence[float]) -> float:
    """An upper bound on the WGS84 length of a longitude/latitude-straight edge."""
    return WGS84_MAX_MERIDIONAL_RADIUS * abs(math.radians(end[1] - start[1])) + (
        WGS84_A * abs(math.radians(end[0] - start[0]))
    )


def _wgs84_distance_to_geometry_m(
    point: Sequence[float], geometry: Mapping[str, Any]
) -> tuple[bool, float]:
    """(covered, metres) from a WGS84 point to a Point/Polygon/MultiPolygon."""
    point = [float(point[0]), float(point[1])]
    if geometry["type"] == "Point":
        target = [float(value) for value in geometry["coordinates"]]
        return point == target, _wgs84_distance_m(point, target)
    polygons = _geometry_polygons(geometry)
    if _covers(polygons, point):
        return True, 0.0
    vertices: dict[tuple[float, float], float] = {}
    edges = []
    for polygon in polygons:
        for ring in polygon:
            for position in ring:
                vertex = (float(position[0]), float(position[1]))
                if vertex not in vertices:
                    vertices[vertex] = _wgs84_distance_m(point, vertex)
            for start, end in zip(ring, ring[1:]):
                a = (float(start[0]), float(start[1]))
                b = (float(end[0]), float(end[1]))
                # Triangle inequality: no edge point is nearer than this bound.
                bound = (vertices[a] + vertices[b] - _edge_length_bound_m(a, b)) / 2
                edges.append((bound, a, b))
    best = min(vertices.values())
    for bound, a, b in sorted(edges):
        if bound >= best:
            break
        best = min(best, _wgs84_edge_distance_m(point, a, b))
    return False, best


def _location_band(covered: bool, distance: float) -> str:
    if covered:
        return "inside"
    if distance <= LOCATION_AGREEMENT_METRES:
        return "within_1000m"
    if distance <= LOCATION_ADJUDICATION_METRES:
        return "adjudication_band"
    return "beyond_3000m"


def blind_review_location_comparison(
    point: Sequence[float], geometry: Mapping[str, Any]
) -> dict[str, Any]:
    """Recompute one pre-registered location comparison.

    ``point`` is the reviewer's [longitude, latitude]; ``geometry`` is a site's
    validated GeoJSON Point, Polygon or MultiPolygon. Returns ``distance_m`` (0
    when inside) and ``band``: ``inside``, ``within_1000m``,
    ``adjudication_band`` (a written adjudication must decide) or
    ``beyond_3000m``. See the module docstring for the method. The distance
    uses platform trigonometry, so it is only ever compared with tolerances and
    thresholds; draft outputs never contain it, which keeps them byte-stable.
    """
    _require(
        isinstance(point, (list, tuple)) and _point(list(point)),
        "blind review point is not WGS84 longitude/latitude",
    )
    _require(
        isinstance(geometry, Mapping)
        and isinstance(geometry.get("type"), str)
        and geometry["type"] in {"Point", "Polygon", "MultiPolygon"},
        "blind review site geometry is not a Point, Polygon or MultiPolygon",
    )
    try:
        positions = _geometry_positions(geometry)
        rings = [ring for polygon in _geometry_polygons(geometry) for ring in polygon]
    except (KeyError, TypeError) as exc:
        raise DraftValidationError("blind review site geometry is malformed") from exc
    _require(
        bool(positions)
        and all(_point(position) for position in positions)
        and all(len(ring) >= 4 and ring[0] == ring[-1] for ring in rings),
        "blind review site geometry is malformed",
    )
    covered, distance = _wgs84_distance_to_geometry_m(point, geometry)
    distance = 0.0 if covered else distance
    return {"distance_m": distance, "band": _location_band(covered, distance)}


def _keys_with_optional(
    value: Any, required: frozenset[str], optional: frozenset[str], label: str
) -> dict[str, Any]:
    _require(
        isinstance(value, dict)
        and set(required) <= set(value) <= set(required) | set(optional),
        f"{label} keys differ",
    )
    return value


def _choice(value: Any, choices: Any, label: str) -> str:
    _require(isinstance(value, str) and value in choices, f"invalid {label}")
    return value


def _review_url(value: Any, label: str) -> str:
    _text(value, label)
    try:
        url = urlsplit(value)
        valid = (
            url.scheme in {"https", "http"}
            and bool(url.hostname)
            and not url.username
            and not url.password
        )
    except ValueError:
        valid = False
    _require(valid, f"invalid {label}")
    return value


def _atlas_surface(url: str) -> bool:
    """Whether a URL names an Atlas surface (``ATLAS_SURFACE_URL_PATTERNS``)."""
    text = url
    for _ in range(3):
        text = unquote(text)
    text = text.lower()
    return any(pattern.search(text) for pattern in ATLAS_SURFACE_URL_PATTERNS)


def _review_day(value: Any, label: str) -> date:
    """A YYYY-MM-DD day, or the written day of an ISO datetime with a timezone."""
    if _date_only(value):
        return _calendar(value, label)
    _require(
        isinstance(value, str)
        and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})",
            value,
        )
        is not None,
        f"{label} must be YYYY-MM-DD or an ISO datetime with a timezone",
    )
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise DraftValidationError(f"invalid {label}") from exc


def _keyed(rows: Sequence[Mapping[str, str]], field: str, label: str) -> dict[str, Any]:
    keyed = {row[field]: row for row in rows}
    _require(len(keyed) == len(rows), f"{label} repeats a {field}")
    return keyed


def _csv_rows(raw: bytes, fields: Sequence[str], label: str) -> list[dict[str, str]]:
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""))
        _require(tuple(reader.fieldnames or ()) == tuple(fields), f"{label} fields differ")
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise DraftValidationError(f"invalid CSV: {label}") from exc
    _require(
        all(None not in row and None not in row.values() for row in rows),
        f"{label} row width differs",
    )
    return rows


def _pinned_review_file(root: Path, value: Any, directory: str, label: str) -> bytes:
    spec = _keys(value, {"path", "bytes", "sha256"}, f"{label} pin")
    path = _portable_path(root, spec["path"], f"{label} path")
    _require(Path(spec["path"]).parts[0] == directory, f"{label} must be under {directory}/")
    return _read_pinned(path, spec["sha256"], spec["bytes"])


def _blind_review_population_release(
    root: Path, population: Mapping[str, Any]
) -> dict[str, list[dict[str, str]]]:
    """Read the pinned projects and sites of the draft a pre-registration names."""
    release = population["release_path"]
    directory = _portable_path(root, release, "pre-registered population release path")
    _require(
        Path(release).parts[0] == "verified_construction_core"
        and not directory.is_symlink()
        and directory.is_dir(),
        "pre-registered population release is not a release directory",
    )
    _require(
        Path(release).as_posix() != BASELINE_RELATIVE_DIR
        and directory.resolve() != (root / BASELINE_RELATIVE_DIR).resolve(),
        "pre-registered population must be a v0.18 draft, not the frozen baseline",
    )
    manifest = _json(
        _read_pinned(
            directory / "manifest.json",
            _hash(population["manifest_sha256"], "pre-registered population manifest"),
        ),
        "pre-registered population manifest",
    )
    _require(
        isinstance(manifest, dict)
        and isinstance(manifest.get("format"), str)
        and manifest["format"] in INHERITED_THROUGH_FORMATS_V3
        and manifest.get("release_status") == "draft"
        and manifest.get("base_preview_manifest_sha256") == BASELINE_MANIFEST_SHA256
        and manifest.get("base_preview_path") == BASELINE_RELATIVE_DIR,
        "pre-registered population is not a v0.18 draft of the pinned v0.17 baseline",
    )
    files = manifest.get("files")
    _require(isinstance(files, dict), "pre-registered population manifest lacks files")
    tables = {}
    for name in ("projects", "sites"):
        entry = files.get(f"{name}.csv")
        _require(
            isinstance(entry, dict) and type(entry.get("bytes")) is int,
            f"pre-registered population manifest lacks {name}.csv",
        )
        raw = _read_pinned(directory / f"{name}.csv", entry.get("sha256"), entry["bytes"])
        tables[name] = _csv_rows(
            raw, TABLE_FIELDS[name], f"pre-registered population {name}.csv"
        )
    return tables


def _blind_review_ranking(seed_sha256: str, keys: Sequence[str]) -> list[tuple[str, str]]:
    """Every key ranked by sha256(seed_sha256 + "|" + key), smallest first."""
    return sorted(
        (hashlib.sha256(f"{seed_sha256}|{key}".encode("utf-8")).hexdigest(), key)
        for key in keys
    )


def _blind_review_preregistration(
    document: Any, root: Path
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Recompute a pre-registration's population, seed, ranking and sample.

    Returns the validated summary and the population release's projects and
    sites keyed by stable key: the rows that were sampled and reviewed.
    """
    _keys(document, PREREGISTRATION_KEYS, "blind review pre-registration")
    _require(
        document["schema_version"] == BLIND_REVIEW_PREREGISTRATION_SCHEMA,
        "blind review pre-registration schema differs",
    )
    registered_at = _calendar(document["registered_at"], "pre-registration date")
    _require(
        registered_at >= LIFECYCLE_REFERENCE_DATE,
        "pre-registration predates the lifecycle cutoff",
    )
    _text(document["purpose"], "pre-registration purpose")
    population = _keys(
        document["population"], PREREGISTRATION_POPULATION_KEYS, "pre-registered population"
    )
    commit = population["published_in_commit"]
    _require(
        isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
        "pre-registered population commit is not a full lower-case git SHA-1",
    )
    keys_sha256 = _hash(
        population["eligible_project_keys_sha256"], "pre-registered population keys"
    )
    count = population["eligible_project_count"]
    _require(
        type(count) is int and count >= BLIND_REVIEW_SAMPLE_SIZE,
        "pre-registered population count is invalid",
    )
    _require(
        population["population_scope"] == BLIND_REVIEW_POPULATION_SCOPE,
        "pre-registered population must be the full expanded eligible population",
    )
    tables = _blind_review_population_release(root, population)
    projects = _keyed(
        tables["projects"], "project_stable_key", "pre-registered population release"
    )
    sites = _keyed(
        tables["sites"], "physical_site_stable_key", "pre-registered population release"
    )
    keys = sorted(projects)
    _require(
        len(keys) == count and canonical_sha256(keys) == keys_sha256,
        "pre-registered population differs from its named release",
    )
    sampling = _keys(
        document["sampling"], PREREGISTRATION_SAMPLING_KEYS, "pre-registered sampling"
    )
    _text(sampling["method"], "pre-registered sampling method")
    material = _text(sampling["seed_material"], "pre-registered seed material")
    _require(
        material == f"{BLIND_REVIEW_SEED_PREFIX}|{keys_sha256}|{commit}",
        "pre-registered seed material is not bound to the population and its commit",
    )
    seed = _hash(sampling["seed_sha256"], "pre-registered seed")
    _require(
        hashlib.sha256(material.encode("utf-8")).hexdigest() == seed,
        "pre-registered seed SHA-256 differs from its seed material",
    )
    _require(
        type(sampling["sample_size"]) is int
        and sampling["sample_size"] == BLIND_REVIEW_SAMPLE_SIZE,
        "pre-registered sample size must be 20",
    )
    _require(
        sampling["formula_fixed_before_draw"] is True,
        "pre-registered sampling formula was not fixed before the draw",
    )
    protocol = _keys(
        document["protocol"], PREREGISTRATION_PROTOCOL_KEYS, "pre-registered protocol"
    )
    _require(
        protocol["lifecycle_reference_date"] == LIFECYCLE_REFERENCE_DATE.isoformat(),
        "pre-registered lifecycle cutoff cannot move",
    )
    _require(
        protocol["physical_observation_window"]
        == [day.isoformat() for day in BLIND_REVIEW_WINDOW],
        "pre-registered observation window differs",
    )
    _require(
        protocol["blind_inputs"] == list(BLIND_REVIEW_INPUTS),
        "pre-registered blind inputs differ",
    )
    for field in ("reviewers", "withheld_from_reviewers", "after_review"):
        _text(protocol[field], f"pre-registered protocol {field}")
    for field, names in PREREGISTRATION_TEXT_BLOCKS:
        block = _keys(protocol[field], names, f"pre-registered protocol {field}")
        for name in sorted(block):
            _text(block[name], f"pre-registered protocol {field} {name}")
    sample = document["sample"]
    _require(
        isinstance(sample, list) and len(sample) == BLIND_REVIEW_SAMPLE_SIZE,
        "pre-registered sample must list 20 positions",
    )
    ranked = _blind_review_ranking(seed, keys)[:BLIND_REVIEW_SAMPLE_SIZE]
    for position, (entry, (rank, key)) in enumerate(zip(sample, ranked), 1):
        _keys(
            entry,
            {"position", "project_stable_key", "rank_sha256", "blind_inputs"},
            "pre-registered sample entry",
        )
        _require(
            type(entry["position"]) is int and entry["position"] == position,
            "pre-registered sample positions must run 1..20 in rank order",
        )
        _require(
            entry["project_stable_key"] == key and entry["rank_sha256"] == rank,
            f"pre-registered sample does not match its seed at position {position}",
        )
        project = projects[key]
        site = sites.get(project["physical_site_stable_key"])
        _require(
            site is not None
            and entry["blind_inputs"]
            == {
                "project_name": project["name"],
                "campus_name": site["name"],
                "country": project["country"],
            },
            f"pre-registered blind inputs differ from the population release at position {position}",
        )
    summary = {
        "registered_at": registered_at,
        "population": population,
        "keys": keys,
        "seed_material": material,
        "seed_sha256": seed,
        "sample": {entry["position"]: entry["project_stable_key"] for entry in sample},
        "reviewers": protocol["reviewers"],
    }
    return summary, {"projects": projects, "sites": sites}


def validate_blind_review_preregistration(
    pin: Mapping[str, Any], *, root: Path = ROOT
) -> dict[str, Any]:
    """Recompute a pinned ``definitions/`` pre-registration against its release.

    ``pin`` is ``{"path", "bytes", "sha256"}``, as in a v3 contract. Returns the
    pre-registered population, its sorted eligible keys, the seed and the
    validated sample by position; raises DraftValidationError otherwise. A v3
    contract additionally requires the pin to be the one that
    ``BLIND_REVIEW_PREREGISTRATIONS`` registers for the population.
    """
    root = Path(root).absolute().resolve()
    raw = _pinned_review_file(root, pin, "definitions", "blind review pre-registration")
    summary, _ = _blind_review_preregistration(
        _json(raw, "blind review pre-registration"), root
    )
    return summary


def _reviewer_output(output: Any, review: Mapping[str, Any], label: str) -> None:
    """A session's optional verbatim output, kept for audit; mapped facts must agree."""
    _require(
        isinstance(output, dict) and bool(output),
        f"{label} reviewer output must be a nonempty object",
    )
    if type(output.get("position")) is int:
        _require(
            output["position"] == review["position"],
            f"{label}: reviewer output names a different position",
        )
    determination = output.get("construction_determination")
    if isinstance(determination, str) and determination in CONSTRUCTION_DETERMINATIONS:
        _require(
            determination == review["construction_determination"],
            f"{label}: reviewer output determination differs from the recorded one",
        )
    place = output.get("location")
    if isinstance(place, dict) and all(
        type(place.get(axis)) in {int, float} for axis in ("longitude", "latitude")
    ):
        location = review["location"]
        _require(
            location["status"] == "located"
            and [location["longitude"], location["latitude"]]
            == [place["longitude"], place["latitude"]],
            f"{label}: reviewer output point differs from the recorded point",
        )


def _blind_review_session(
    review: Any, registered_at: date, recorded_at: date
) -> dict[str, Any]:
    """Validate one reviewer session; return it with its date and blindness facts."""
    _require(isinstance(review, dict), "blind review session is not an object")
    aborted = (
        _choice(
            review.get("session_status"),
            {"completed", "aborted"},
            "blind review session status",
        )
        == "aborted"
    )
    if aborted:
        _keys(review, ABORTED_SESSION_KEYS, "aborted blind review session")
    else:
        _keys_with_optional(
            review,
            REVIEW_KEYS,
            UNCOUNTED_SESSION_KEYS | {"reviewer_output"},
            "blind review",
        )
    position = review["position"]
    _require(
        type(position) is int and 1 <= position <= BLIND_REVIEW_SAMPLE_SIZE,
        "blind review position must be 1..20",
    )
    label = f"blind review at position {position}"
    _text(review["project_stable_key"], f"{label} project key")
    _text(review["reviewer_session_id"], f"{label} session ID")
    _require(
        type(review["session_sequence"]) is int and review["session_sequence"] >= 1,
        f"{label} session_sequence must be a positive integer",
    )
    reviewed_at = _calendar(review["reviewed_at"], f"{label} date")
    _require(
        registered_at <= reviewed_at <= recorded_at,
        f"{label} is dated outside pre-registration..recording",
    )
    _require(type(review["counted"]) is bool, f"{label} counted must be true or false")
    if aborted:
        _require(review["counted"] is False, f"{label}: an aborted session is never counted")
    _require(
        all(review["counted"] == (key not in review) for key in UNCOUNTED_SESSION_KEYS),
        f"{label}: exactly the uncounted sessions carry uncounted_reason and "
        "counted_session_id",
    )
    if not review["counted"]:
        _choice(review["uncounted_reason"], UNCOUNTED_REASONS, f"{label} uncounted reason")
        _text(review["counted_session_id"], f"{label} counted session ID")
    if aborted:
        _text(review["abort_notes"], f"{label} abort notes")
        return {
            "review": review,
            "reviewed_at": reviewed_at,
            "blind": False,
            "atlas_materials_accessed": None,
            "atlas_surface_urls": [],
        }
    determination = _choice(
        review["construction_determination"],
        CONSTRUCTION_DETERMINATIONS,
        f"{label} construction determination",
    )
    evidence = review["construction_evidence"]
    _require(isinstance(evidence, list), f"{label} construction evidence is not a list")
    urls = []
    observed_in_window = False
    for item in evidence:
        _keys_with_optional(
            item,
            REVIEW_EVIDENCE_KEYS,
            REVIEW_EVIDENCE_OPTIONAL_KEYS,
            f"{label} construction evidence",
        )
        urls.append(_review_url(item["source_url"], f"{label} evidence source URL"))
        observed = _calendar(item["observation_date"], f"{label} observation date")
        _require(observed <= reviewed_at, f"{label} observation follows its review")
        _text(item["literal_pointer"], f"{label} evidence literal pointer")
        _hash(item["capture_sha256"], f"{label} evidence capture")
        for field in sorted(REVIEW_EVIDENCE_OPTIONAL_KEYS.intersection(item)):
            _text(item[field], f"{label} evidence {field}")
        if "retrieved_at" in item:
            retrieved = _review_day(item["retrieved_at"], f"{label} evidence retrieval")
            _require(
                observed <= retrieved <= reviewed_at,
                f"{label} evidence retrieval must fall between its observation and the review",
            )
        observed_in_window |= BLIND_REVIEW_WINDOW[0] <= observed <= BLIND_REVIEW_WINDOW[1]
    successor = _keys(review["successor_check"], {"status", "notes"}, f"{label} successor check")
    status = _choice(successor["status"], SUCCESSOR_CHECK_STATUSES, f"{label} successor status")
    _text(successor["notes"], f"{label} successor notes")
    if determination == "under_construction_in_window":
        _require(
            observed_in_window,
            f"{label}: under_construction_in_window needs an observation inside the window",
        )
        _require(
            status == "none_found_on_or_before_cutoff",
            f"{label}: under_construction_in_window needs no completion, opening or "
            "cancellation found on or before the cutoff",
        )
    elif determination == "not_under_construction_in_window":
        _require(bool(evidence), f"{label}: not_under_construction_in_window needs evidence")
    location = _keys_with_optional(
        review["location"],
        REVIEW_LOCATION_KEYS,
        REVIEW_LOCATION_OPTIONAL_KEYS,
        f"{label} location",
    )
    located = (
        _choice(location["status"], {"located", "unable_to_locate"}, f"{label} location status")
        == "located"
    )
    if located:
        _require(
            _point([location["longitude"], location["latitude"]]),
            f"{label} point is not finite WGS84 longitude/latitude",
        )
        _text(location["method"], f"{label} location method")
        urls.append(_review_url(location["source_url"], f"{label} location source URL"))
    else:
        _require(
            location["longitude"] is None and location["latitude"] is None,
            f"{label}: unable_to_locate carries no coordinates",
        )
        _require("notes" in location, f"{label}: unable_to_locate needs notes")
        if location["method"] is not None:
            _text(location["method"], f"{label} location method")
        if location["source_url"] is not None:
            urls.append(_review_url(location["source_url"], f"{label} location source URL"))
    for field in ("literal_pointer", "notes"):
        if field in location:
            _text(location[field], f"{label} location {field}")
    if "capture_sha256" in location:
        _hash(location["capture_sha256"], f"{label} location capture")
    _text(review["identity_notes"], f"{label} identity notes")
    attestation = _keys(
        review["blindness_attestation"],
        {"atlas_materials_accessed", "statement"},
        f"{label} blindness attestation",
    )
    _require(
        type(attestation["atlas_materials_accessed"]) is bool,
        f"{label} blindness attestation must be true or false",
    )
    _text(attestation["statement"], f"{label} blindness statement")
    if "reviewer_output" in review:
        _reviewer_output(review["reviewer_output"], review, label)
    atlas = sorted({url for url in urls if _atlas_surface(url)})
    return {
        "review": review,
        "reviewed_at": reviewed_at,
        "blind": attestation["atlas_materials_accessed"] is False and not atlas,
        "atlas_materials_accessed": attestation["atlas_materials_accessed"],
        "atlas_surface_urls": atlas,
    }


def _recorded_distance_in_band(rule: str, distance: float) -> bool:
    if rule == "inside":
        return distance == 0
    if rule == "within_1000m":
        return distance <= LOCATION_AGREEMENT_METRES
    if rule in ADJUDICATED_LOCATION_RULES:
        return LOCATION_AGREEMENT_METRES < distance <= LOCATION_ADJUDICATION_METRES
    return distance > LOCATION_ADJUDICATION_METRES


def _blind_review_comparison(
    row: Any,
    position: int,
    key: str,
    review: Mapping[str, Any],
    release: Mapping[str, Mapping[str, Mapping[str, str]]],
    session_ids: set[str],
    adjudication_window: tuple[date, date],
) -> dict[str, Any]:
    """Recompute one comparison row against the pre-registered release's geometry."""
    _keys_with_optional(row, COMPARISON_KEYS, frozenset({"notes"}), "blind review comparison")
    label = f"comparison at position {position}"
    _require(
        type(row["position"]) is int and row["position"] == position,
        "blind review comparison positions must run 1..20 in order",
    )
    _require(row["project_stable_key"] == key, f"{label} names a different project")
    if "notes" in row:
        _text(row["notes"], f"{label} notes")
    construction = review["construction_determination"] == "under_construction_in_window"
    _require(
        row["construction_agrees"] is construction,
        f"{label}: construction agreement differs from the determination",
    )
    rule = _choice(row["location_rule"], LOCATION_RULES, f"{label} location rule")
    distance = row["location_distance_m"]
    adjudication = row["adjudication"]
    location = review["location"]
    if location["status"] == "unable_to_locate":
        _require(
            rule == "unable_to_locate" and distance is None and adjudication is None,
            f"{label}: an unlocated review compares as unable_to_locate with no distance "
            "or adjudication",
        )
    else:
        _require(rule != "unable_to_locate", f"{label}: the review located a point")
        # The sampled rows are the reviewed ones: never the checkpoint being built,
        # whose later edits cannot re-score a review.
        site = release["sites"][release["projects"][key]["physical_site_stable_key"]]
        recomputed = blind_review_location_comparison(
            [location["longitude"], location["latitude"]],
            _json_field(site["geometry_json"], "pre-registered site geometry"),
        )
        computed, band = recomputed["distance_m"], recomputed["band"]
        _require(
            type(distance) in {int, float} and math.isfinite(distance) and distance >= 0,
            f"{label}: location distance must be finite metres",
        )
        _require(
            abs(distance - computed)
            <= max(DISTANCE_TOLERANCE_METRES, DISTANCE_TOLERANCE_FRACTION * computed),
            f"{label}: recorded distance differs from the recomputed {computed:.1f} m",
        )
        if band == "adjudication_band":
            _require(
                rule in ADJUDICATED_LOCATION_RULES,
                f"{label}: 1,000-3,000 m needs a written adjudication",
            )
        else:
            _require(
                rule not in ADJUDICATED_LOCATION_RULES,
                f"{label}: adjudication is accepted only in the 1,000-3,000 m band",
            )
            _require(rule == band, f"{label}: location rule differs from the recomputed {band}")
        _require(
            _recorded_distance_in_band(rule, distance),
            f"{label}: recorded distance {distance} m lies outside the {rule} band",
        )
        if rule in ADJUDICATED_LOCATION_RULES:
            _require(
                isinstance(adjudication, dict),
                f"{label}: 1,000-3,000 m needs a written adjudication",
            )
            _keys(adjudication, ADJUDICATION_KEYS, f"{label} adjudication")
            _require(
                _text(adjudication["adjudicated_by"], f"{label} adjudicator")
                not in session_ids,
                f"{label}: the adjudicator must not be a reviewer session",
            )
            adjudicated_at = _calendar(
                adjudication["adjudicated_at"], f"{label} adjudication date"
            )
            _require(
                adjudication_window[0] <= adjudicated_at <= adjudication_window[1],
                f"{label}: adjudication must follow every counted review and precede "
                "the recording",
            )
            _text(adjudication["reason"], f"{label} adjudication reason")
        else:
            _require(
                adjudication is None, f"{label}: only an adjudicated rule has an adjudication"
            )
    agreement = construction and rule in AGREEING_LOCATION_RULES
    _require(
        row["agreement"] is agreement, f"{label}: agreement differs from the recomputation"
    )
    # Report the pinned recorded distance, never the platform-computed float.
    return {
        "position": position,
        "project_stable_key": key,
        "reviewer_session_id": review["reviewer_session_id"],
        "session_sequence": review["session_sequence"],
        "construction_determination": review["construction_determination"],
        "construction_agrees": construction,
        "location_rule": rule,
        "recorded_location_distance_m": distance,
        "adjudication": None
        if adjudication is None
        else {field: adjudication[field] for field in sorted(ADJUDICATION_KEYS)},
        "agreement": agreement,
    }


def _counted_sessions(
    sessions: Sequence[Mapping[str, Any]], sample: Mapping[int, str]
) -> tuple[dict[int, Mapping[str, Any]], list[dict[str, Any]]]:
    """Apply ``BLIND_REVIEW_COUNTED_SESSION_RULE``: the counted session is fixed."""
    groups: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for item in sessions:
        position = item["review"]["position"]
        _require(
            item["review"]["project_stable_key"] == sample[position],
            f"blind review at position {position} names a different project",
        )
        groups[position].append(item)
    counted: dict[int, Mapping[str, Any]] = {}
    for position, group in groups.items():
        flagged = [item for item in group if item["review"]["counted"]]
        _require(len(flagged) <= 1, f"position {position} has more than one counted review")
        if flagged:
            counted[position] = flagged[0]
    missing = sorted(set(sample) - set(counted))
    _require(
        not missing,
        "every pre-registered position needs exactly one counted review; missing: "
        + ", ".join(str(position) for position in missing),
    )
    uncounted = []
    for position in sorted(groups):
        chosen = counted[position]
        label = f"blind review at position {position}"
        _require(
            chosen["atlas_materials_accessed"] is False,
            f"{label}: a counted session must not have accessed Atlas materials",
        )
        _require(
            not chosen["atlas_surface_urls"],
            f"{label}: a counted session cites an Atlas surface: "
            + ", ".join(chosen["atlas_surface_urls"]),
        )
        group = sorted(groups[position], key=lambda item: item["review"]["session_sequence"])
        earliest = next(item for item in group if item["blind"])
        _require(
            earliest is chosen,
            f"{label}: the counted session must be the earliest blind completed session, "
            + earliest["review"]["reviewer_session_id"],
        )
        for item in group:
            if item is chosen:
                continue
            review = item["review"]
            session = review["reviewer_session_id"]
            _require(
                review["counted_session_id"] == chosen["review"]["reviewer_session_id"],
                f"uncounted session at position {position} must name its counted session",
            )
            reason = (
                "aborted"
                if review["session_status"] == "aborted"
                else "later_duplicate"
                if item["blind"]
                else "blindness_breach"
            )
            _require(
                review["uncounted_reason"] == reason,
                f"uncounted session {session} at position {position} is {reason}, "
                f"not {review['uncounted_reason']}",
            )
            uncounted.append(
                {
                    "position": position,
                    "project_stable_key": review["project_stable_key"],
                    "reviewer_session_id": session,
                    "session_sequence": review["session_sequence"],
                    "session_status": review["session_status"],
                    "reviewed_at": review["reviewed_at"],
                    "uncounted_reason": reason,
                    "counted_session_id": review["counted_session_id"],
                    "construction_determination": review.get("construction_determination"),
                    "location_status": review["location"]["status"]
                    if "location" in review
                    else None,
                    "atlas_materials_accessed": item["atlas_materials_accessed"],
                    "atlas_surface_urls": item["atlas_surface_urls"],
                }
            )
    uncounted.sort(key=lambda entry: entry["session_sequence"])
    return counted, uncounted


def _blind_review_results(
    record: Any,
    preregistration: Mapping[str, Any],
    release: Mapping[str, Mapping[str, Mapping[str, str]]],
    pin: Mapping[str, Any],
    contract_reviewed_at: date,
) -> dict[str, Any]:
    """Validate a results record and recompute every comparison and the totals."""
    _keys(record, RESULTS_KEYS, "blind review results")
    _require(
        record["schema_version"] == BLIND_REVIEW_RESULTS_SCHEMA,
        "blind review results schema differs",
    )
    registered_at = preregistration["registered_at"]
    recorded_at = _calendar(record["recorded_at"], "blind review results date")
    _require(
        registered_at <= recorded_at <= contract_reviewed_at,
        "blind review results must be recorded after pre-registration and by the "
        "contract review date",
    )
    binding = _keys(record["preregistration"], {"path", "sha256"}, "results pre-registration")
    _require(
        binding == {"path": pin["path"], "sha256": pin["sha256"]},
        "blind review results name a different pre-registration",
    )
    _require(
        isinstance(record["population"], dict)
        and canonical_sha256(record["population"])
        == canonical_sha256(preregistration["population"]),
        "blind review results population differs from the pre-registration",
    )
    sample = preregistration["sample"]
    reviews = record["reviews"]
    _require(isinstance(reviews, list) and bool(reviews), "blind review results list no reviews")
    sessions = [_blind_review_session(review, registered_at, recorded_at) for review in reviews]
    session_ids = [item["review"]["reviewer_session_id"] for item in sessions]
    _require(len(set(session_ids)) == len(session_ids), "blind reviewer session IDs repeat")
    sequences = [item["review"]["session_sequence"] for item in sessions]
    _require(len(set(sequences)) == len(sequences), "blind review session sequences repeat")
    counted, uncounted = _counted_sessions(sessions, sample)
    disclosures = _unique_text(record["disclosures"], "blind review disclosures")
    comparison = record["comparison"]
    _require(
        isinstance(comparison, list) and len(comparison) == BLIND_REVIEW_SAMPLE_SIZE,
        "blind review comparison must list all 20 positions",
    )
    # Adjudication is part of the comparison, made after every counted review.
    window = (max(item["reviewed_at"] for item in counted.values()), recorded_at)
    outcomes = [
        _blind_review_comparison(
            row,
            position,
            sample[position],
            counted[position]["review"],
            release,
            set(session_ids),
            window,
        )
        for position, row in enumerate(comparison, 1)
    ]
    agreements = sum(item["agreement"] for item in outcomes)
    totals = _keys(
        record["totals"], {"sample_size", "agreements", "gate_passed"}, "blind review totals"
    )
    _require(
        type(totals["sample_size"]) is int
        and totals["sample_size"] == BLIND_REVIEW_SAMPLE_SIZE
        and type(totals["agreements"]) is int
        and totals["agreements"] == agreements
        and totals["gate_passed"] is (agreements >= BLIND_REVIEW_REQUIRED_AGREEMENTS),
        "blind review totals differ from the recomputation",
    )
    rules = Counter(item["location_rule"] for item in outcomes)
    return {
        "recorded_at": recorded_at,
        "sample_size": len(outcomes),
        "agreements": agreements,
        "construction_agreements": sum(item["construction_agrees"] for item in outcomes),
        "location_agreements": sum(
            item["location_rule"] in AGREEING_LOCATION_RULES for item in outcomes
        ),
        "location_rule_counts": {rule: rules[rule] for rule in LOCATION_RULES},
        "uncounted_sessions": uncounted,
        "outcomes": outcomes,
        "disclosures": list(disclosures),
    }


def _blind_review_claims(
    projects: Mapping[str, Mapping[str, str]], sites: Mapping[str, Mapping[str, str]]
) -> dict[str, list[Any]]:
    """Each project's blind-reviewed claims (``BLIND_REVIEW_*_CLAIM_FIELDS``)."""
    claims = {}
    for key, row in projects.items():
        site = sites.get(row["physical_site_stable_key"])
        claims[key] = [
            [row[field] for field in BLIND_REVIEW_PROJECT_CLAIM_FIELDS],
            None if site is None else [site[field] for field in BLIND_REVIEW_SITE_CLAIM_FIELDS],
        ]
    return claims


def _blind_review(
    batch: ValidatedBatch,
    delta: Mapping[str, list[dict[str, Any]]],
    reviewed_at: date,
) -> dict[str, Any]:
    """Validate a v3 contract's pinned pre-registration and results record."""
    entry = _keys(batch.contract["blind_review"], {"preregistration", "results"}, "blind review")
    pins = {}
    raw = {}
    for name, directory in (("preregistration", "definitions"), ("results", "sources")):
        raw[name] = _pinned_review_file(
            batch.root, entry[name], directory, f"blind review {name}"
        )
        pins[name] = {field: entry[name][field] for field in ("path", "bytes", "sha256")}
    preregistration, release = _blind_review_preregistration(
        _json(raw["preregistration"], "blind review pre-registration"), batch.root
    )
    registered = BLIND_REVIEW_PREREGISTRATIONS.get(
        preregistration["population"]["manifest_sha256"]
    )
    _require(
        registered is not None and dict(registered) == pins["preregistration"],
        "blind review pre-registration is not the one registered in builder code for "
        "its population",
    )
    results = _blind_review_results(
        _json(raw["results"], "blind review results"),
        preregistration,
        release,
        pins["preregistration"],
        reviewed_at,
    )
    # The checkpoint being built, read back exactly as its CSV files will read.
    _, inherited_raw, _ = _inherited(batch)
    tables = _table_bytes(inherited_raw, delta)
    current = {
        name: _keyed(
            _csv_rows(tables[f"{name}.csv"], TABLE_FIELDS[name], f"draft {name}.csv"),
            field,
            f"draft {name}.csv",
        )
        for name, field in (
            ("projects", "project_stable_key"),
            ("sites", "physical_site_stable_key"),
        )
    }
    reviewed_claims = _blind_review_claims(release["projects"], release["sites"])
    current_claims = _blind_review_claims(current["projects"], current["sites"])
    return {
        "preregistration": {
            **pins["preregistration"],
            "registered_at": preregistration["registered_at"].isoformat(),
            "seed_material": preregistration["seed_material"],
            "seed_sha256": preregistration["seed_sha256"],
        },
        "results_record": {
            **pins["results"],
            "recorded_at": results["recorded_at"].isoformat(),
        },
        "reviewed_population": dict(preregistration["population"]),
        "reviewed_project_keys": list(preregistration["keys"]),
        "current_project_keys": sorted(current_claims),
        "projects_with_changed_claims": sorted(
            key
            for key in set(reviewed_claims) & set(current_claims)
            if reviewed_claims[key] != current_claims[key]
        ),
        "sample": dict(preregistration["sample"]),
        "reviewers": preregistration["reviewers"],
        **{key: value for key, value in results.items() if key != "recorded_at"},
    }


def _blind_review_gate(
    summary: Mapping[str, Any],
    projects: Sequence[Mapping[str, Any]],
    inherited_blind: Any,
    withdrawals: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """The v3 gate: evaluated only for exactly the pre-registered population.

    A project removed by a baseline withdrawal is absent from this checkpoint,
    so a withdrawn reviewed project always makes the population differ and a
    withdrawn sampled project can never pass or be re-scored.
    """
    keys = sorted(row["project_stable_key"] for row in projects)
    _require(
        keys == summary["current_project_keys"],
        "draft projects differ from the validated blind review",
    )
    reviewed = summary["reviewed_project_keys"]
    changed = summary["projects_with_changed_claims"]
    population = summary["reviewed_population"]
    matches = keys == reviewed and not changed
    withdrawn = {
        item["entry"]["project_stable_key"]: item["withdrawal_id"] for item in withdrawals
    }
    _require(
        not withdrawn.keys() & set(keys)
        and not (matches and withdrawn.keys() & set(reviewed)),
        "a withdrawn project cannot remain in a matching blind-review population",
    )
    mismatch = None
    if not matches:
        current = set(keys)
        mismatch = {
            "reviewed_release_path": population["release_path"],
            "reviewed_manifest_sha256": population["manifest_sha256"],
            "reviewed_eligible_project_count": len(reviewed),
            "reviewed_eligible_project_keys_sha256": population[
                "eligible_project_keys_sha256"
            ],
            "current_eligible_project_count": len(keys),
            "current_eligible_project_keys_sha256": canonical_sha256(keys),
            "current_projects_not_in_reviewed_population": sorted(current - set(reviewed)),
            "reviewed_projects_not_in_current_population": sorted(set(reviewed) - current),
            "projects_with_changed_reviewed_claims": changed,
            "sampled_positions_not_covered": [
                position
                for position, key in sorted(summary["sample"].items())
                if key not in current or key in changed
            ],
            "reason": "The pinned blind review sampled a different eligible population: its project keys, or the identity, status or location claims of its projects, differ from this checkpoint's. Its result is reported but cannot pass this checkpoint's gate; a new pre-registered sample of the current eligible population is required.",
        }
        if withdrawals:
            # Reported only by a checkpoint with withdrawals, so v3 checkpoints
            # without them keep their exact report bytes.
            mismatch["reviewed_projects_withdrawn"] = sorted(
                withdrawn.keys() & set(reviewed)
            )
            mismatch["sampled_projects_withdrawn"] = [
                {
                    "position": position,
                    "project_stable_key": key,
                    "withdrawal_id": withdrawn[key],
                }
                for position, key in sorted(summary["sample"].items())
                if key in withdrawn
            ]
    sample_size, agreements = summary["sample_size"], summary["agreements"]
    record_passed = (
        sample_size == BLIND_REVIEW_SAMPLE_SIZE
        and agreements >= BLIND_REVIEW_REQUIRED_AGREEMENTS
    )
    return {
        "sample_size": sample_size,
        "agreements": agreements,
        "required_sample_size": BLIND_REVIEW_SAMPLE_SIZE,
        "required_agreements": BLIND_REVIEW_REQUIRED_AGREEMENTS,
        "eligible_project_count": len(keys),
        "eligible_project_stable_keys": keys,
        "eligible_project_keys_sha256": canonical_sha256(keys),
        "population_scope": BLIND_REVIEW_POPULATION_SCOPE,
        "sample_scope": "the pinned pre-registered fixed 20-project blind review, drawn from exactly this checkpoint's eligible population: the same project keys and blind-reviewed claims"
        if matches
        else "the pinned pre-registered blind review was drawn from a different eligible population (see population_mismatch); its inherited result is reported but does not cover this checkpoint",
        "inherited_baseline_review": inherited_blind,
        "population_matches": matches,
        "population_mismatch": mismatch,
        "reviewed_population": population,
        "reviewed_claim_fields": {
            "projects": list(BLIND_REVIEW_PROJECT_CLAIM_FIELDS),
            "sites": list(BLIND_REVIEW_SITE_CLAIM_FIELDS),
        },
        "preregistration": summary["preregistration"],
        "results_record": summary["results_record"],
        "reviewed_population_gate_passed": record_passed,
        "construction_agreements": summary["construction_agreements"],
        "location_agreements": summary["location_agreements"],
        "location_rule_counts": summary["location_rule_counts"],
        "counted_session_rule": BLIND_REVIEW_COUNTED_SESSION_RULE,
        "uncounted_review_sessions": summary["uncounted_sessions"],
        "sample_outcomes": summary["outcomes"],
        "disagreement_positions": [
            item["position"] for item in summary["outcomes"] if not item["agreement"]
        ],
        "location_method": BLIND_REVIEW_LOCATION_METHOD,
        "reviewers": summary["reviewers"],
        "disclosures": summary["disclosures"],
        "passed": matches and record_passed,
    }


def validate_batch(
    contract_path: Path, review_pins: ReviewPins, *, root: Path = ROOT
) -> ValidatedBatch:
    """Phase one: read-only validation against independently supplied review pins."""
    supplied_root = Path(root).absolute()
    root = supplied_root.resolve()
    contract_path = Path(contract_path)
    if not contract_path.is_absolute():
        relative_contract = contract_path
    elif contract_path.is_relative_to(supplied_root):
        relative_contract = contract_path.relative_to(supplied_root)
    else:
        _require(contract_path.is_relative_to(root), "contract must be inside root")
        relative_contract = contract_path.relative_to(root)
    contract_path = _portable_path(root, relative_contract.as_posix(), "contract path")
    contract = _json(
        _read_pinned(contract_path, review_pins.contract_sha256), "batch contract"
    )
    # Only a v2 or v3 contract may carry baseline_corrections and only a v3
    # contract a blind_review and, optionally, baseline_withdrawals; v1 and v2
    # keep their exact keys.
    schema_version = contract.get("schema_version") if isinstance(contract, dict) else None
    blind_review_enabled = schema_version == SCHEMA_VERSION_V3
    corrections_enabled = schema_version == SCHEMA_VERSION_V2 or blind_review_enabled
    withdrawals_enabled = blind_review_enabled and "baseline_withdrawals" in contract
    _keys(
        contract,
        CONTRACT_KEYS_V3 | {"baseline_withdrawals"}
        if withdrawals_enabled
        else CONTRACT_KEYS_V3
        if blind_review_enabled
        else CONTRACT_KEYS_V2
        if corrections_enabled
        else CONTRACT_KEYS,
        "batch contract",
    )
    _require(
        contract["schema_version"] == SCHEMA_VERSION or corrections_enabled,
        "batch schema version differs",
    )
    _require(
        isinstance(review_pins.baseline_correction_sha256, Mapping)
        and (corrections_enabled or not review_pins.baseline_correction_sha256),
        "baseline correction review pins require a v2 contract",
    )
    _require(
        isinstance(review_pins.baseline_withdrawal_sha256, Mapping)
        and (withdrawals_enabled or not review_pins.baseline_withdrawal_sha256),
        "baseline withdrawal review pins require a v3 contract with baseline_withdrawals",
    )
    if blind_review_enabled:
        _require(
            isinstance(review_pins.blind_review_sha256, str)
            and canonical_sha256(contract["blind_review"])
            == review_pins.blind_review_sha256,
            "independent blind review pin differs",
        )
    else:
        _require(
            review_pins.blind_review_sha256 is None
            or review_pins.blind_review_sha256 == "",
            "a blind review pin requires a v3 contract",
        )
    _require(
        re.fullmatch(
            r"[a-z0-9][a-z0-9-]{0,95}", _text(contract["batch_id"], "batch ID")
        )
        is not None,
        "unsafe batch ID",
    )
    _require(
        contract["base_preview_manifest_sha256"] == BASELINE_MANIFEST_SHA256,
        "batch baseline pin differs",
    )
    _require(
        contract["lifecycle_reference_date"] == LIFECYCLE_REFERENCE_DATE.isoformat(),
        "lifecycle cutoff cannot move",
    )
    reviewed_at = _calendar(
        contract["geometry_identity_reviewed_at"], "geometry review date"
    )
    _require(
        reviewed_at >= LIFECYCLE_REFERENCE_DATE,
        "geometry review predates lifecycle cutoff",
    )
    baseline = _load_baseline(root)
    base_campuses = {row["physical_site_stable_key"] for row in baseline["sites"]}
    base_projects = {row["project_stable_key"] for row in baseline["projects"]}
    base_evidence = {row["evidence_id"] for row in baseline["evidence"]}
    source_specs = contract["sources"]
    _require(
        isinstance(source_specs, list) and bool(source_specs), "batch sources missing"
    )
    sources = {}
    evidence_by_id = {}
    date_only_sources: set[str] = set()
    for spec in source_specs:
        _keys(
            spec,
            {
                "source_id",
                "path",
                "bytes",
                "sha256",
                "evidence_pointer",
                "evidence_sha256",
            },
            "source spec",
        )
        source_id = _text(spec["source_id"], "source ID")
        _require(source_id not in sources, "duplicate source ID")
        _require(
            canonical_sha256(spec) == review_pins.source_sha256.get(source_id),
            f"independent source review pin differs: {source_id}",
        )
        path = _portable_path(root, spec["path"], "source path")
        _require(
            Path(spec["path"]).parts[0] == "sources", "source must be under sources/"
        )
        document = _json(_read_pinned(path, spec["sha256"], spec["bytes"]), source_id)
        evidence = _pointer(document, spec["evidence_pointer"])
        _require(
            canonical_sha256(evidence)
            == _hash(spec["evidence_sha256"], "evidence record hash"),
            "evidence record SHA-256 differs",
        )
        # A v2 date-only retrieval must later prove it is a correction's reused
        # frozen capture; v1 and every other source keep the timezone rule.
        inherited_date = (
            corrections_enabled
            and isinstance(evidence, dict)
            and _date_only(evidence.get("retrieved_at"))
        )
        projection = _source_evidence(
            evidence, source_id, inherited_date_only_retrieval=inherited_date
        )
        if inherited_date:
            date_only_sources.add(source_id)
        identifier = projection["evidence_id"]
        _require(
            identifier not in base_evidence,
            "baseline evidence ID reuse would alter frozen usage rows",
        )
        _require(
            identifier not in evidence_by_id or evidence_by_id[identifier] == evidence,
            "conflicting evidence with the same derived ID",
        )
        evidence_by_id[identifier] = evidence
        retrieval_day = datetime.fromisoformat(
            evidence["retrieved_at"].replace("Z", "+00:00")
        ).date()
        _require(
            retrieval_day <= reviewed_at,
            "source retrieval follows geometry-identity review",
        )
        sources[source_id] = {
            "spec": spec,
            "document": document,
            "evidence": evidence,
            "projection": projection,
        }
    _require(
        set(sources) == set(review_pins.source_sha256),
        "source review pin inventory differs",
    )
    acceptances = contract["acceptances"]
    _require(
        isinstance(acceptances, list) and bool(acceptances), "batch acceptances missing"
    )
    campus_keys = [
        _text(item.get("parent_campus_stable_key"), "parent campus key")
        for item in acceptances
        if isinstance(item, dict)
    ]
    _require(
        len(campus_keys) == len(acceptances)
        and len(campus_keys) == len(set(campus_keys)),
        "duplicate or invalid batch campus",
    )
    batch_keys_sha = canonical_sha256(sorted(campus_keys))
    base_keys_sha = canonical_sha256(sorted(base_campuses))
    aliases_seen: set[str] = set(base_campuses)
    anchors_seen = {
        (float(row["longitude"]), float(row["latitude"])) for row in baseline["sites"]
    }
    projects_seen = set(base_projects)
    countries = {row["country"]: row["country_iso_a2"] for row in baseline["sites"]}
    names_by_iso = {iso: name for name, iso in countries.items()}
    used_sources: set[str] = set()
    validated = []
    for acceptance in acceptances:
        _keys(
            acceptance,
            {
                "project_stable_key",
                "parent_campus_stable_key",
                "country_iso_a2",
                "identity",
                "status",
                "geometry",
                "distinctness_review",
            },
            "acceptance",
        )
        project_key = _text(acceptance["project_stable_key"], "project key")
        campus_key = acceptance["parent_campus_stable_key"]
        _require(project_key not in projects_seen, "duplicate or baseline project key")
        projects_seen.add(project_key)
        _require(
            canonical_sha256(acceptance)
            == review_pins.acceptance_sha256.get(project_key),
            f"independent acceptance review pin differs: {project_key}",
        )
        identity = _keys(
            acceptance["identity"],
            {
                "source_id",
                "project_pointer",
                "project_sha256",
                "campus_pointer",
                "campus_sha256",
            },
            "identity binding",
        )
        project = _record(
            sources,
            identity["source_id"],
            identity["project_pointer"],
            identity["project_sha256"],
            "project identity",
        )
        campus = _record(
            sources,
            identity["source_id"],
            identity["campus_pointer"],
            identity["campus_sha256"],
            "campus identity",
        )
        _require(
            project.get("stable_key") == project_key
            and campus.get("stable_key") == campus_key,
            "source project/campus identity differs",
        )
        _text(project.get("name"), "project name")
        _text(campus.get("name"), "campus name")
        country = _text(project.get("country"), "project country")
        _require(campus.get("country") == country, "campus/project country differs")
        iso = acceptance["country_iso_a2"]
        _require(
            isinstance(iso, str) and iso in ISO_A2_CODES, "invalid ISO alpha-2 code"
        )
        _require(
            countries.get(country, iso) == iso
            and names_by_iso.get(iso, country) == country,
            "country/ISO mapping conflicts",
        )
        countries[country] = iso
        names_by_iso[iso] = country
        for entity in (project, campus):
            _require(
                entity.get("country_iso_a2", iso) == iso, "source country ISO differs"
            )
        status_binding = _keys(
            acceptance["status"],
            {"source_id", "record_pointer", "record_sha256"},
            "status binding",
        )
        status = _record(
            sources,
            status_binding["source_id"],
            status_binding["record_pointer"],
            status_binding["record_sha256"],
            "status",
        )
        _require(
            status.get("entity") == "project"
            and isinstance(status.get("value"), str)
            and status["value"] in core.PHYSICAL_STATUSES
            and isinstance(status.get("method"), str)
            and status["method"] in core.AUTHORITATIVE_STATUS_METHODS,
            "status is not authoritative physical work",
        )
        age = (
            LIFECYCLE_REFERENCE_DATE
            - _calendar(status.get("as_of_date"), "status date")
        ).days
        _require(0 <= age <= 90, "status outside fixed 90-day window")
        _require(
            status.get("evidence_key")
            == sources[status_binding["source_id"]]["evidence"]["key"],
            "status evidence key differs",
        )
        status_source_project = sources[status_binding["source_id"]]["document"].get(
            "project"
        )
        _require(
            isinstance(status_source_project, dict)
            and status_source_project.get("stable_key") == project_key,
            "status source does not bind exact project",
        )
        status_source_campus = sources[status_binding["source_id"]]["document"].get(
            "campus"
        )
        _require(
            isinstance(status_source_campus, dict)
            and status_source_campus.get("stable_key") == campus_key,
            "status source does not bind exact campus",
        )
        geometry_binding = _keys(
            acceptance["geometry"],
            {"source_id", "record_pointer", "record_sha256"},
            "geometry binding",
        )
        geometry = _record(
            sources,
            geometry_binding["source_id"],
            geometry_binding["record_pointer"],
            geometry_binding["record_sha256"],
            "geometry",
        )
        _geometry(geometry)
        _require(
            geometry["project_stable_key"] == project_key
            and geometry["parent_campus_stable_key"] == campus_key,
            "geometry project/campus identity differs",
        )
        geometry_ids = _unique_text(
            geometry["geometry_source_ids"], "geometry source IDs"
        )
        identity_ids = _unique_text(
            geometry["identity_source_ids"], "geometry identity source IDs"
        )
        _require(
            geometry_binding["source_id"] in geometry_ids,
            "primary geometry source is not a geometry evidence source",
        )
        _require(
            identity["source_id"] in identity_ids,
            "identity source missing from geometry identity bindings",
        )
        anchor = tuple(
            float(value) for value in geometry["display_anchor"]["coordinates"]
        )
        _require(
            anchor not in anchors_seen,
            "coincident baseline/batch locator needs duplicate-site adjudication",
        )
        anchors_seen.add(anchor)
        review = _keys(
            acceptance["distinctness_review"],
            {
                "decision",
                "scope",
                "equivalent_campus_keys",
                "baseline_site_keys_sha256",
                "batch_site_keys_sha256",
                "evidence_source_ids",
                "reason",
            },
            "distinctness review",
        )
        _require(
            review["decision"] == "distinct_physical_site"
            and review["scope"] == "single_physical_site",
            "distinct physical-site scope not resolved",
        )
        aliases = set(
            _unique_text(review["equivalent_campus_keys"], "equivalent campus keys")
        )
        _require(
            campus_key in aliases and not aliases.intersection(aliases_seen),
            "campus alias duplicates baseline or batch site",
        )
        aliases_seen.update(aliases)
        _require(
            review["baseline_site_keys_sha256"] == base_keys_sha
            and review["batch_site_keys_sha256"] == batch_keys_sha,
            "distinctness review comparison set differs",
        )
        review_sources = _unique_text(
            review["evidence_source_ids"], "distinctness evidence IDs"
        )
        _require(
            identity["source_id"] in review_sources
            and bool(set(geometry_ids).intersection(review_sources)),
            "distinctness review lacks identity and geometry evidence",
        )
        _text(review["reason"], "distinctness decision reason")
        used = set(
            geometry_ids
            + identity_ids
            + review_sources
            + [identity["source_id"], status_binding["source_id"]]
        )
        _require(used.issubset(sources), "unbound acceptance source ID")
        used_sources.update(used)
        validated.append(
            {
                "acceptance": acceptance,
                "project": project,
                "campus": campus,
                "status": status,
                "geometry": geometry,
            }
        )
    _require(
        set(review_pins.acceptance_sha256) == projects_seen - base_projects,
        "acceptance review pin inventory differs",
    )
    corrections: list[dict[str, Any]] = []
    if corrections_enabled:
        corrections = _baseline_corrections(
            contract["baseline_corrections"],
            root,
            baseline,
            sources,
            review_pins,
            reviewed_at,
            set(used_sources),
            date_only_sources,
            allow_empty=blind_review_enabled,
            formats=INHERITED_THROUGH_FORMATS_V3
            if blind_review_enabled
            else INHERITED_THROUGH_FORMATS_V2,
        )
        for correction in corrections:
            used_sources.update(correction["geometry_source_ids"])
    _require(used_sources == set(sources), "unused source documents are not allowed")
    withdrawals: list[dict[str, Any]] = []
    if withdrawals_enabled:
        # Validated before any row is derived: every later step, including the
        # blind-review population comparison, reads the post-withdrawal rows.
        withdrawals = _baseline_withdrawals(
            contract["baseline_withdrawals"],
            root,
            baseline,
            review_pins,
            reviewed_at,
            corrections,
        )
    batch = ValidatedBatch(
        root,
        contract_path,
        review_pins,
        contract,
        baseline,
        sources,
        tuple(validated),
        tuple(corrections),
        baseline_withdrawals=tuple(withdrawals),
    )
    delta = None
    if corrections:
        # The evidence deltas depend on acceptance usage, so phase one derives
        # them once here; build and validate_draft derive them again identically.
        delta = _delta_rows(batch)
        _intersecting_rows_unchanged(batch, delta)
    if blind_review_enabled:
        # The blind review is recomputed against the pre-registered release's rows,
        # and this checkpoint's rows are compared with them for the gate.
        blind_review = _blind_review(
            batch, delta if delta is not None else _delta_rows(batch), reviewed_at
        )
        batch = replace(batch, blind_review=blind_review)
    return batch


def _delta_rows(batch: ValidatedBatch) -> dict[str, list[dict[str, Any]]]:
    projects = []
    sites = []
    evidence_pool = {}
    usage: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"roles": set(), "projects": set()}
    )
    for item in sorted(
        batch.acceptances, key=lambda value: value["acceptance"]["project_stable_key"]
    ):
        acceptance, project, campus, status, locator = (
            item[key]
            for key in ("acceptance", "project", "campus", "status", "geometry")
        )
        key, campus_key = (
            acceptance["project_stable_key"],
            acceptance["parent_campus_stable_key"],
        )
        project_id = core.atlas_stable_id("entity", key, "project")
        site_id = core._stable_id("vcc-site", campus_key)
        primary_geometry_id = acceptance["geometry"]["source_id"]
        status_source_id = acceptance["status"]["source_id"]
        roles_by_source: dict[str, set[str]] = defaultdict(set)
        roles_by_source[status_source_id].add("physical_status")
        for source_id in locator["geometry_source_ids"]:
            roles_by_source[source_id].add("geometry")
        for source_id in locator["identity_source_ids"]:
            roles_by_source[source_id].add("context:geometry_identity")
        for source_id in acceptance["distinctness_review"]["evidence_source_ids"]:
            roles_by_source[source_id].add("context:site_distinctness")
        for source_id, roles in roles_by_source.items():
            evidence = batch.sources[source_id]["projection"]
            identifier = evidence["evidence_id"]
            evidence_pool[identifier] = evidence
            usage[identifier]["roles"].update(roles)
            usage[identifier]["projects"].add(project_id)
        semantics = locator["semantics"]
        geometry = locator["geometry"]
        longitude, latitude = locator["display_anchor"]["coordinates"]
        uncertainty = semantics["horizontal_uncertainty_metres"]
        row = {field: "" for field in core.PROJECT_FIELDS}
        row.update(
            {
                "project_id": project_id,
                "project_stable_key": key,
                "site_id": site_id,
                "physical_site_stable_key": campus_key,
                "name": project["name"],
                "country": project["country"],
                "country_iso_a2": acceptance["country_iso_a2"],
                "latitude": latitude,
                "longitude": longitude,
                "geometry_json": core._json_bytes(geometry).decode().strip(),
                "geometry_type": geometry["type"],
                **{
                    field: semantics[field]
                    for field in SEMANTIC_FIELDS
                    if field.startswith("geometry_")
                },
                "geometry_precision_scope": semantics["precision_scope"],
                "horizontal_uncertainty_metres": ""
                if uncertainty is None
                else uncertainty,
                "horizontal_uncertainty_unknown_reason": semantics[
                    "horizontal_uncertainty_unknown_reason"
                ],
                "geometry_evidence_id": batch.sources[primary_geometry_id][
                    "projection"
                ]["evidence_id"],
                "last_observed_physical_status": status["value"],
                "status_as_of": status["as_of_date"],
                "status_age_days_at_review": (
                    LIFECYCLE_REFERENCE_DATE - date.fromisoformat(status["as_of_date"])
                ).days,
                "status_method": status["method"],
                "status_evidence_id": batch.sources[status_source_id]["projection"][
                    "evidence_id"
                ],
                "verification_posture": _verification_posture(
                    semantics["geometry_authority_class"],
                    semantics["geometry_use_scope"],
                ),
                "independent_imagery_verification": "false",
                "imagery_review_outcome": "not_reviewed_for_core_preview",
                "development_type": "unknown",
                "development_type_unknown_reason": "not selected by this reviewed draft batch",
                "operating_model": "unknown",
                "operating_model_unknown_reason": "not established by selected evidence",
                "workloads_json": "[]",
                "workload_unknown_reason": "not established by selected evidence",
                "role_claims_json": "[]",
                "power_observations_json": "[]",
                "power_unknown_reason": "no typed power observation selected; not estimated",
                "annual_energy_observations_json": "[]",
                "annual_energy_unknown_reason": "no scoped annual-energy inputs selected; not estimated",
                "efficiency_observations_json": "[]",
                "efficiency_unknown_reason": "no scoped PUE or WUE observation selected",
                "status_source_url": batch.sources[status_source_id]["projection"][
                    "source_url"
                ],
                "geometry_source_url": batch.sources[primary_geometry_id]["projection"][
                    "source_url"
                ],
            }
        )
        projects.append(row)
        site = {field: "" for field in core.SITE_FIELDS}
        site.update(
            {
                field: row[field]
                for field in (
                    "site_id",
                    "physical_site_stable_key",
                    "country",
                    "country_iso_a2",
                    "latitude",
                    "longitude",
                    "geometry_json",
                    "geometry_type",
                    "horizontal_uncertainty_metres",
                    "horizontal_uncertainty_unknown_reason",
                    "verification_posture",
                    "independent_imagery_verification",
                )
            }
        )
        site.update(
            {
                "name": campus["name"],
                "project_count": 1,
                "oldest_status_as_of": status["as_of_date"],
                "newest_status_as_of": status["as_of_date"],
            }
        )
        list_fields = {
            "geometry_source_entity_kinds_json": [
                semantics["geometry_source_entity_kind"]
            ],
            "geometry_derivations_json": [semantics["geometry_derivation"]],
            "geometry_methods_json": [semantics["geometry_method"]],
            "geometry_scope_classes_json": [semantics["geometry_scope_class"]],
            "geometry_authority_classes_json": [semantics["geometry_authority_class"]],
            "geometry_use_scopes_json": [semantics["geometry_use_scope"]],
            "geometry_precision_scopes_json": [semantics["precision_scope"]],
            "geometry_evidence_ids_json": sorted(
                {
                    batch.sources[source_id]["projection"]["evidence_id"]
                    for source_id in locator["geometry_source_ids"]
                }
            ),
            "project_ids_json": [project_id],
            "project_stable_keys_json": [key],
            "statuses_json": [status["value"]],
            "imagery_review_outcomes_json": ["not_reviewed_for_core_preview"],
        }
        site.update(
            {
                field: core._json_bytes(value).decode().strip()
                for field, value in list_fields.items()
            }
        )
        sites.append(site)
    # Baseline corrections: geometry-only usage of the correction sources. A row
    # enumerated as added must be new; a shared row must already exist through
    # an acceptance with that role and only gains the project association.
    acceptance_roles = {
        identifier: frozenset(item["roles"]) for identifier, item in usage.items()
    }
    for correction in batch.baseline_corrections:
        project_id = correction["project"]["project_id"]
        delta = correction["evidence_delta"]
        added = {item["evidence_id"] for item in delta["added"]}
        shared = {item["evidence_id"] for item in delta["association_only"]}
        for source_id in correction["geometry_source_ids"]:
            evidence = batch.sources[source_id]["projection"]
            identifier = evidence["evidence_id"]
            if identifier in shared:
                _require(
                    "geometry" in acceptance_roles.get(identifier, frozenset()),
                    "association-only correction evidence must already carry its role",
                )
            else:
                _require(
                    identifier in added and identifier not in acceptance_roles,
                    "added correction evidence is already used by an acceptance",
                )
            evidence_pool[identifier] = evidence
            usage[identifier]["roles"].add("geometry")
            usage[identifier]["projects"].add(project_id)
    for correction in batch.baseline_corrections:
        for item in correction["evidence_delta"]["added"]:
            usage_item = usage[item["evidence_id"]]
            _require(
                sorted(usage_item["roles"]) == item["roles"]
                and sorted(usage_item["projects"]) == item["project_ids"],
                "added correction evidence row differs from its enumerated delta",
            )
    evidence_rows = [
        {
            **evidence_pool[identifier],
            "roles_json": core._json_bytes(sorted(item["roles"])).decode().strip(),
            "project_ids_json": core._json_bytes(sorted(item["projects"]))
            .decode()
            .strip(),
        }
        for identifier, item in sorted(usage.items())
    ]
    return {"projects": projects, "sites": sites, "evidence": evidence_rows}


def _inherited(
    batch: ValidatedBatch,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, bytes], list[Any]]:
    """Inherited rows, raw CSV bytes and features, with pinned corrections applied.

    Without corrections or withdrawals these are the frozen v0.17 rows, bytes
    and features. A correction replaces exactly its project/site lines and
    feature with the validated derivations and drops the superseded evidence
    lines; a withdrawal drops its project, site and evidence lines and its
    feature. Every other inherited line keeps its frozen bytes and order.
    """
    rows = {name: batch.baseline[name] for name in TABLE_FIELDS}
    raw = {name: batch.baseline["files"][f"{name}.csv"] for name in TABLE_FIELDS}
    features = _json(batch.baseline["files"]["sites.geojson"], "baseline GeoJSON")[
        "features"
    ]
    if not batch.baseline_corrections and not batch.baseline_withdrawals:
        return rows, raw, features
    rows = {name: list(value) for name, value in rows.items()}
    lines = {
        name: _csv_lines(raw[name], len(rows[name]), f"frozen {name}.csv")
        for name in TABLE_FIELDS
    }
    features = list(features)
    dropped: dict[str, set[int]] = {name: set() for name in TABLE_FIELDS}
    for correction in batch.baseline_corrections:
        located = correction["located"]
        for table, key in (("projects", "project"), ("sites", "site")):
            index = located[table]["index"]
            rows[table][index] = correction[key]
            lines[table][index + 1] = _csv_line(correction[key], TABLE_FIELDS[table])
        dropped["evidence"].add(located["evidence"]["index"])
        dropped["evidence"].update(item["index"] for item in located["additional_evidence"])
        features[located["feature"]["index"]] = correction["feature"]
    removed_features: set[int] = set()
    for withdrawal in batch.baseline_withdrawals:
        located = withdrawal["located"]
        dropped["projects"].add(located["projects"]["index"])
        dropped["sites"].add(located["sites"]["index"])
        dropped["evidence"].update(item["index"] for item in located["evidence"])
        removed_features.add(located["feature"]["index"])
    for name in TABLE_FIELDS:
        rows[name] = [row for index, row in enumerate(rows[name]) if index not in dropped[name]]
        # Line 0 is the header and the last element the empty string after the
        # final newline; data line number n holds row index n - 1.
        lines[name] = [
            line for number, line in enumerate(lines[name]) if number - 1 not in dropped[name]
        ]
    features = [
        feature for index, feature in enumerate(features) if index not in removed_features
    ]
    return rows, {name: b"\n".join(value) for name, value in lines.items()}, features


def _table_bytes(
    inherited_raw: Mapping[str, bytes], delta: Mapping[str, list[dict[str, Any]]]
) -> dict[str, bytes]:
    """The draft's CSV files: the inherited bytes, then the delta rows."""
    return {
        f"{name}.csv": inherited_raw[name]
        + core._csv_bytes(delta[name], fields).split(b"\n", 1)[1]
        for name, fields in (
            ("projects", core.PROJECT_FIELDS),
            ("sites", core.SITE_FIELDS),
            ("evidence", core.EVIDENCE_FIELDS),
        )
    }


def _payloads(batch: ValidatedBatch) -> tuple[dict[str, bytes], dict[str, Any]]:
    # v3 is v2 plus the pinned blind review and optional baseline withdrawals;
    # v1 and v2 outputs, and v3 outputs without withdrawals, are unchanged.
    blind = batch.contract["schema_version"] == SCHEMA_VERSION_V3
    corrected = batch.contract["schema_version"] == SCHEMA_VERSION_V2 or blind
    withdrawn = blind and "baseline_withdrawals" in batch.contract
    _require(
        blind == (batch.blind_review is not None),
        "a v3 draft needs exactly its validated blind review",
    )
    _require(
        withdrawn == bool(batch.baseline_withdrawals),
        "a draft with baseline withdrawals needs exactly its validated v3 withdrawals",
    )
    delta = _delta_rows(batch)
    inherited_rows, inherited_raw, inherited_features = _inherited(batch)
    tables = {name: [*inherited_rows[name], *delta[name]] for name in delta}
    projects, sites, evidence = (
        tables[name] for name in ("projects", "sites", "evidence")
    )
    for name, field in (
        ("projects", "project_id"),
        ("sites", "site_id"),
        ("evidence", "evidence_id"),
    ):
        _require(
            len({row[field] for row in tables[name]}) == len(tables[name]),
            f"duplicate {name} output ID",
        )
    if batch.baseline_corrections:
        output_evidence = {row["evidence_id"] for row in evidence}
        for correction in batch.baseline_corrections:
            referenced = {
                correction["project"]["geometry_evidence_id"],
                correction["project"]["status_evidence_id"],
                *_json_field(
                    correction["site"]["geometry_evidence_ids_json"],
                    "corrected site evidence",
                ),
            }
            _require(
                referenced.issubset(output_evidence)
                and not output_evidence.intersection(
                    correction["superseded_evidence_ids"]
                ),
                "corrected rows and output evidence differ",
            )
    if withdrawn:
        # Nothing that remains may name a withdrawn project, site or evidence
        # row, and every remaining evidence row is used by a remaining project.
        removed = {
            identifier
            for withdrawal in batch.baseline_withdrawals
            for identifier in (
                withdrawal["located"]["projects"]["row"]["project_id"],
                withdrawal["located"]["sites"]["row"]["site_id"],
                *withdrawal["located"]["evidence_ids"],
            )
        }
        _require(
            not any(
                identifier in str(value)
                for table in tables.values()
                for row in table
                for value in row.values()
                for identifier in removed
            ),
            "a remaining row references a withdrawn project, site or evidence row",
        )
        output_projects = {row["project_id"] for row in projects}
        _require(
            all(
                bool(_json_field(row["project_ids_json"], "evidence projects"))
                and set(_json_field(row["project_ids_json"], "evidence projects"))
                <= output_projects
                for row in evidence
            ),
            "a remaining evidence row is not used by a remaining project",
        )
    country_counts = dict(sorted(Counter(row["country"] for row in sites).items()))
    imagery_counts = dict(
        sorted(Counter(row["imagery_review_outcome"] for row in projects).items())
    )
    reviewed_imagery = sum(
        count
        for outcome, count in imagery_counts.items()
        if outcome != "not_reviewed_for_core_preview"
    )
    base_report = _json(
        batch.baseline["files"]["selection-report.json"], "baseline report"
    )
    inherited_blind = base_report["final_release_gates"]["blind_review"]
    baseline_count = len(batch.baseline["sites"])
    target = baseline_count + TARGET_ADDITIONAL_SITES
    non_us = sum(row["country_iso_a2"] != "US" for row in sites)
    official_boundaries = sum(core._is_official_boundary(row) for row in projects)
    counts = {
        "physical_sites": len(sites),
        "projects": len(projects),
        "evidence": len(evidence),
        "countries": len(country_counts),
        "non_us_sites": non_us,
        "official_boundary_projects": official_boundaries,
        "reviewed_site_locator_projects": sum(
            _is_reviewed_locator(row) for row in projects
        ),
    }
    if corrected:
        counts["host_estate_context_projects"] = sum(
            _is_host_estate_context(row) for row in projects
        )
    gates = {
        "site_count": {
            "actual": len(sites),
            "required": target,
            "passed": len(sites) >= target,
        },
        "additional_site_count": {
            "actual": len(sites) - baseline_count,
            "required": TARGET_ADDITIONAL_SITES,
            "passed": len(sites) - baseline_count >= TARGET_ADDITIONAL_SITES,
        },
        "country_count": {
            "actual": len(country_counts),
            "required_minimum": 40,
            "passed": len(country_counts) >= 40,
        },
        "non_us_site_count": {
            "actual": non_us,
            "required_minimum": 100,
            "passed": non_us >= 100,
        },
        "maximum_single_country_share": {
            "actual": max(country_counts.values()) / len(sites),
            "required_maximum": 0.4,
            "passed": max(country_counts.values()) / len(sites) <= 0.4,
        },
        "imagery_outcomes_complete": {
            "actual": reviewed_imagery,
            "required": len(projects),
            "passed": reviewed_imagery == len(projects),
        },
        "blind_review": {
            "sample_size": 0,
            "agreements": 0,
            "required_sample_size": 20,
            "required_agreements": 19,
            "eligible_project_count": len(projects),
            "eligible_project_stable_keys": sorted(
                row["project_stable_key"] for row in projects
            ),
            "eligible_project_keys_sha256": canonical_sha256(
                sorted(row["project_stable_key"] for row in projects)
            ),
            "population_scope": "all expanded projects, including inherited baseline and reviewed draft additions",
            "sample_scope": "no expanded-population blind-review sample or agreement records supplied by this draft builder",
            "inherited_baseline_review": inherited_blind,
            "passed": False,
        },
        "clean_clone_rebuild": {
            "passed": False,
            "reason": "portable inputs are hash-bound; an actual clean-clone run is an external release check",
        },
        "publication_authorized": {
            "passed": False,
            "reason": "this builder emits opt-in drafts only",
        },
    }
    if blind:
        gates["blind_review"] = _blind_review_gate(
            batch.blind_review, projects, inherited_blind, batch.baseline_withdrawals
        )
    if withdrawn:
        # Only a checkpoint with withdrawals carries this gate, so v3 checkpoints
        # without them keep their exact report bytes.
        gates[WITHDRAWAL_SHARED_CAPTURE_GATE] = _shared_capture_gate(
            batch.baseline_withdrawals, projects, evidence
        )
    report = {
        "format": "datacenter-atlas-v018-draft-selection-v3"
        if blind
        else "datacenter-atlas-v018-draft-selection-v2"
        if corrected
        else "datacenter-atlas-v018-draft-selection-v1",
        "batch_id": batch.contract["batch_id"],
        "release_status": "draft",
        "publishable_as_final": False,
        "objective_completion_claim": False,
        "accepted_into_published_core": False,
        "lifecycle_reference_date": LIFECYCLE_REFERENCE_DATE.isoformat(),
        "geometry_identity_reviewed_at": batch.contract[
            "geometry_identity_reviewed_at"
        ],
        "baseline_counts": batch.baseline["manifest"]["counts"],
        "counts": counts,
        "draft_delta_counts": {
            "physical_sites": len(delta["sites"]),
            "projects": len(delta["projects"]),
            "evidence": len(delta["evidence"]),
        },
        "country_counts": country_counts,
        "imagery_outcome_counts": imagery_counts,
        "final_release_gates": gates,
        "source_review_limits": "Pinned source facts and reviewer decisions are reproducible; machine validation does not independently establish physical truth or resolve undisclosed campus aliases.",
    }
    provenance = {
        "contract_path": batch.contract_path.relative_to(batch.root).as_posix(),
        "contract_sha256": batch.pins.contract_sha256,
        "independent_source_review_sha256": dict(batch.pins.source_sha256),
        "independent_acceptance_review_sha256": dict(batch.pins.acceptance_sha256),
        "source_inputs": batch.contract["sources"],
        "acceptances": batch.contract["acceptances"],
    }
    if corrected:
        report["baseline_corrections"] = [
            _correction_report(correction, batch)
            for correction in batch.baseline_corrections
        ]
        report["locator_exceptions"] = _locator_exceptions(
            projects, sites, batch.baseline_corrections
        )
        provenance["independent_baseline_correction_review_sha256"] = dict(
            batch.pins.baseline_correction_sha256
        )
        provenance["baseline_corrections"] = batch.contract["baseline_corrections"]
    if blind:
        provenance["independent_blind_review_sha256"] = batch.pins.blind_review_sha256
        provenance["blind_review"] = batch.contract["blind_review"]
    withdrawal_summary: dict[str, Any] = {}
    if withdrawn:
        withdrawal_summary = _withdrawals_summary(batch.baseline_withdrawals, sites)
        report["baseline_withdrawals"] = withdrawal_summary
        provenance["independent_baseline_withdrawal_review_sha256"] = dict(
            batch.pins.baseline_withdrawal_sha256
        )
        provenance["baseline_withdrawals"] = batch.contract["baseline_withdrawals"]
    geojson = _json(batch.baseline["files"]["sites.geojson"], "baseline GeoJSON")
    geojson = {
        **geojson,
        "name": "Data Center Atlas v0.18 expansion draft",
        "release_status": "draft",
        "features": [
            *inherited_features,
            *core._geojson(delta["sites"])["features"],
        ],
    }
    schema = _json(batch.baseline["files"]["schema.json"], "baseline schema")
    schema["format"] = "datacenter-atlas-verified-construction-core-schema-v018-draft"
    schema["base_preview_id"] = schema.pop("preview_id")
    schema["draft_id"] = f"2026-08-20-v0.18-draft-{batch.contract['batch_id']}"
    schema.pop("map")
    inherited_annotation_keys = [key for key in schema if key.startswith("v0_")]
    schema["inherited_baseline_annotations"] = {
        "preview_id": schema["base_preview_id"],
        "manifest_sha256": BASELINE_MANIFEST_SHA256,
        "scope": "historical annotations and counts for frozen v0.17 records only; not current expanded-cohort accounting",
        "annotations": {key: schema.pop(key) for key in inherited_annotation_keys},
    }
    for table_name, table_schema in schema["tables"].items():
        current_rows = tables[table_name.removesuffix(".csv")]
        for field in table_schema["fields"]:
            if "allowed_values" in field and field["logical_type"] == "string":
                field["allowed_values"] = sorted(
                    set(field["allowed_values"])
                    | {row[field["name"]] for row in current_rows}
                )
                field["allowed_values_scope"] = (
                    "frozen baseline schema plus values in reviewed draft rows"
                    + (
                        " and pinned baseline corrections"
                        if corrected and batch.baseline_corrections
                        else ""
                    )
                    + (
                        "; pinned baseline withdrawals remove rows but add no value"
                        if withdrawn
                        else ""
                    )
                )
    schema["v018_draft_contract"] = {
        "schema_version": batch.contract["schema_version"],
        "release_status": "draft",
        "publishable_as_final": False,
        "location_bases": sorted(LOCATION_BASES),
        "geometry_use_scopes": sorted(USE_SCOPES),
        "schema_documentation": "datacenter_atlas/verified_construction_core_v018.py module docstring",
    }
    if corrected:
        schema["v018_draft_contract"].update(
            {
                "baseline_correction_location_bases": sorted(
                    BASELINE_CORRECTION_LOCATION_BASES
                ),
                "baseline_correction_geometry_source_entity_kinds": sorted(
                    BASELINE_CORRECTION_ENTITY_KINDS
                ),
                "baseline_correction_geometry_use_scopes": sorted(
                    BASELINE_CORRECTION_USE_SCOPES
                ),
                "baseline_correction_verification_postures": [
                    HOST_ESTATE_CONTEXT_POSTURE
                ],
                "baseline_correction_scope": "Accepted only through pinned baseline corrections of inherited v0.17 rows, never for acceptances. Host-estate context is not a reviewed site locator, official boundary or site position, and is excluded from reviewed_site_locator_projects.",
            }
        )
    if blind:
        schema["v018_draft_contract"].update(
            {
                "blind_review_preregistration_schema": BLIND_REVIEW_PREREGISTRATION_SCHEMA,
                "blind_review_results_schema": BLIND_REVIEW_RESULTS_SCHEMA,
                "blind_review_location_rules": list(LOCATION_RULES),
                "blind_review_agreeing_location_rules": sorted(AGREEING_LOCATION_RULES),
                "blind_review_location_method": BLIND_REVIEW_LOCATION_METHOD,
                "blind_review_counted_session_rule": BLIND_REVIEW_COUNTED_SESSION_RULE,
                "blind_review_claim_fields": {
                    "projects": list(BLIND_REVIEW_PROJECT_CLAIM_FIELDS),
                    "sites": list(BLIND_REVIEW_SITE_CLAIM_FIELDS),
                },
                "blind_review_gate": "Evaluated only when this draft is exactly the pre-registered population: the same sorted eligible project keys and, for every project, the same blind-reviewed claim values. At least 19 of the 20 pre-registered projects must then agree on construction and location, recomputed against the pre-registered release. A different population is reported with population_mismatch and never passes.",
            }
        )
    if withdrawn:
        schema["v018_draft_contract"].update(
            {
                "baseline_withdrawal_record_schema": BASELINE_WITHDRAWAL_RECORD_SCHEMA,
                "baseline_withdrawal_decisions": [BASELINE_WITHDRAWAL_DECISION],
                "baseline_withdrawal_bases": sorted(BASELINE_WITHDRAWAL_BASES),
                "baseline_withdrawal_claim_boundary": dict(
                    BASELINE_WITHDRAWAL_CLAIM_BOUNDARY
                ),
                "baseline_withdrawal_ids": sorted(
                    item["withdrawal_id"] for item in batch.baseline_withdrawals
                ),
                "baseline_withdrawal_scope": "Accepted only through pinned schema-v3 baseline withdrawals of inherited v0.17 projects on single-project sites. A withdrawal removes the project row, its site row, its GeoJSON feature and every evidence row only it referenced, and changes no other byte. It asserts no physical status (not paused, cancelled, completed or not under construction); the withdrawn project's status on the lifecycle reference date is unknown, and no status value is added. Selected rows that share a withdrawn row's source capture (the same source URL and content hash) are neither changed nor re-reviewed; they keep the withdrawal_shared_capture_review final-release gate open.",
                "baseline_withdrawal_shared_capture_gate": WITHDRAWAL_SHARED_CAPTURE_GATE,
            }
        )
    attribution = (
        batch.baseline["files"]["ATTRIBUTION.txt"]
        + b"\n\nV0.18 DRAFT ADDITIONAL SOURCE ATTRIBUTION\n"
    )
    for source_id, source in sorted(batch.sources.items()):
        row = source["projection"]
        attribution += (
            f"\n{source_id}\n{row['attribution']}\n{row['license']}\n{row['source_url']}\nSource input: {source['spec']['path']}\n"
        ).encode()

    def plural(count: int, noun: str) -> str:
        return f"{count} {noun}{'' if count == 1 else 's'}"

    preservation = "All inherited rows and features are preserved. "
    corrections_detail = ""
    # v2 always has a correction; a v3 draft without one keeps the v1 wording.
    if corrected and batch.baseline_corrections:
        rescoped = len(batch.baseline_corrections)
        removed = sum(
            len(item["evidence_delta"]["removed"]) for item in batch.baseline_corrections
        )
        shared = len(
            {
                row["evidence_id"]
                for item in batch.baseline_corrections
                for row in item["evidence_delta"]["association_only"]
            }
        )
        associations = sum(
            len(item["evidence_delta"]["association_only"])
            for item in batch.baseline_corrections
        )
        corrections_detail = (
            "the enumerated fields of "
            f"{plural(rescoped, 're-scoped project row')}, "
            f"{plural(rescoped, 'site row')} and {plural(rescoped, 'feature')}; "
            f"{plural(removed, 'superseded evidence row')} dropped; and "
            + (
                f"{plural(shared, 'shared evidence row')} gaining only the corrected "
                "project association"
                if associations == shared
                else f"{plural(shared, 'shared evidence row')} gaining only "
                f"{associations} corrected project associations"
            )
        )
    withdrawals_detail = ""
    if withdrawn:
        effect = withdrawal_summary["count_effect"]
        withdrawals_detail = (
            f"{plural(-effect['projects'], 'project row')}, "
            f"{plural(-effect['physical_sites'], 'site row')}, "
            f"{plural(-effect['physical_sites'], 'feature')} and "
            f"{plural(-effect['evidence'], 'evidence row')}"
        )
    if corrections_detail and withdrawals_detail:
        preservation = (
            "All inherited rows and features are preserved, except the changes made "
            f"by pinned baseline corrections ({corrections_detail}) and the rows "
            f"removed by pinned baseline withdrawals ({withdrawals_detail}). "
        )
    elif corrections_detail:
        preservation = (
            "All inherited rows and features are preserved, except the changes made "
            f"by pinned baseline corrections: {corrections_detail}. "
        )
    elif withdrawals_detail:
        preservation = (
            "All inherited rows and features are preserved, except the rows removed "
            f"by pinned baseline withdrawals: {withdrawals_detail}. "
        )
    corrections_text = ""
    if corrected and batch.baseline_corrections:
        correction_count = len(batch.baseline_corrections)
        host_estate = counts["host_estate_context_projects"]
        correction_ids = ", ".join(
            sorted(item["correction_id"] for item in batch.baseline_corrections)
        )
        corrections_text = (
            f"Baseline corrections: {correction_count} pinned versioned "
            f"correction{'' if correction_count == 1 else 's'} ({correction_ids}) "
            f"re-scope{'s' if correction_count == 1 else ''} inherited locator "
            "semantics and evidence only; no site, project, geometry, display anchor "
            "or lifecycle observation is added, removed or moved. "
            f"{host_estate} counted project{'' if host_estate == 1 else 's'} "
            f"{'has' if host_estate == 1 else 'have'} host-estate locality context only, "
            "not a reviewed site locator; such a display anchor is not a site position. "
            "See selection-report.json baseline_corrections and locator_exceptions.\n\n"
        )
    withdrawals_text = ""
    delta_sentence = (
        f"The frozen v0.17 baseline has {baseline_count} sites; this reviewed draft adds "
        f"{len(delta['sites'])}. "
    )
    if withdrawn:
        effect = withdrawal_summary["count_effect"]
        count = len(batch.baseline_withdrawals)
        one = count == 1
        withdrawal_ids = ", ".join(
            sorted(item["withdrawal_id"] for item in batch.baseline_withdrawals)
        )
        lost = withdrawal_summary["countries_without_selected_site"]
        affected = gates[WITHDRAWAL_SHARED_CAPTURE_GATE]["projects"]
        single = len(affected) == 1
        shared_text = (
            f"{plural(len(affected), 'selected project')} ({', '.join(affected)}) "
            f"{'keeps' if single else 'keep'} evidence from the same source capture (the same "
            "URL and content hash) as a withdrawn evidence row; a withdrawal neither changes "
            f"nor re-reviews {'it' if single else 'them'}, so the "
            f"{WITHDRAWAL_SHARED_CAPTURE_GATE} gate is not passed. "
            if affected
            else "No selected project shares a source capture with a withdrawn evidence row. "
        )
        delta_sentence = (
            f"The frozen v0.17 baseline has {baseline_count} sites; this reviewed draft adds "
            f"{len(delta['sites'])} and withdraws {-effect['physical_sites']}. "
        )
        withdrawals_text = (
            f"Baseline withdrawals: {count} pinned versioned "
            f"withdrawal{'' if one else 's'} ({withdrawal_ids}) "
            f"remove{'s' if one else ''} {plural(-effect['projects'], 'inherited project')} "
            f"and {plural(-effect['physical_sites'], 'site')} from the selection, because "
            f"{'its' if one else 'their'} selected evidence does not meet the acceptance "
            f"contract, and drop{'s' if one else ''} the "
            f"{plural(-effect['evidence'], 'evidence row')} that only "
            f"{'it' if one else 'they'} referenced. A withdrawal asserts no physical "
            "status: it does not claim that a project is paused, cancelled, completed or "
            "not under construction, and a withdrawn project's physical status on "
            f"{LIFECYCLE_REFERENCE_DATE.isoformat()} is unknown. "
            + (f"No selected site remains in {', '.join(lost)}. " if lost else "")
            + shared_text
            + "ATTRIBUTION.txt keeps every inherited v0.17 notice, including notices for "
            "sources that only withdrawn rows used. "
            + "See selection-report.json baseline_withdrawals.\n\n"
        )
    blind_text = (
        f"Imagery outcomes: {reviewed_imagery}/{len(projects)}; additional blind reviews: 0. "
    )
    if blind:
        gate = gates["blind_review"]
        result = f"{gate['agreements']}/{gate['sample_size']} agreements"
        if gate["population_matches"]:
            blind_text = (
                f"Imagery outcomes: {reviewed_imagery}/{len(projects)}. "
                f"Blind review: {result} in the pre-registered fixed sample of all "
                f"{len(projects)} eligible projects; the blind-review gate (at least "
                f"{BLIND_REVIEW_REQUIRED_AGREEMENTS} of {BLIND_REVIEW_SAMPLE_SIZE}) is "
                f"{'passed' if gate['passed'] else 'not passed'}. "
            )
        else:
            blind_text = (
                f"Imagery outcomes: {reviewed_imagery}/{len(projects)}. "
                f"Blind review: the pinned pre-registered result ({result}) was drawn "
                "from a different eligible population "
                f"({gate['reviewed_population']['eligible_project_count']} projects, "
                "whose keys or blind-reviewed claims differ), not this checkpoint's "
                f"{len(projects)} projects, so the blind-review gate is not passed. "
            )
            sampled_withdrawn = gate["population_mismatch"].get(
                "sampled_projects_withdrawn", []
            )
            if sampled_withdrawn:
                single = len(sampled_withdrawn) == 1
                blind_text += (
                    f"Sampled position{'' if single else 's'} "
                    + ", ".join(str(item["position"]) for item in sampled_withdrawn)
                    + f" {'was' if single else 'were'} removed by a pinned baseline "
                    "withdrawal and cannot be re-scored against this checkpoint. "
                )
        uncounted = len(gate["uncounted_review_sessions"])
        if uncounted:
            blind_text += (
                f"{uncounted} further review session{'' if uncounted == 1 else 's'} "
                f"{'was' if uncounted == 1 else 'were'} recorded but not counted under "
                "the counted-session rule; see selection-report.json. "
            )
        blind_text += (
            "The blind reviewers were independent AI research agents, not human "
            "reviewers. "
        )
    readme = (
        f"# Data Center Atlas v0.18 expansion draft\n\n"
        f"{counts['physical_sites']} physical sites, {counts['projects']} projects, {counts['countries']} countries. "
        f"{delta_sentence}"
        f"The requested expansion target remains {target} total sites ({TARGET_ADDITIONAL_SITES} additional).\n\n"
        "This is an opt-in local draft, not a public release or a claim of goal completion. "
        "The public builder still defaults to v0.17. "
        f"{preservation}"
        "Locators are not building footprints or surveyed boundaries unless their explicit semantics say otherwise. "
        "No additional roles, workloads, capacities, energy, or efficiency observations are inferred.\n\n"
        f"{corrections_text}"
        f"{withdrawals_text}"
        f"Lifecycle cutoff: {LIFECYCLE_REFERENCE_DATE.isoformat()}. "
        f"{blind_text}"
        "See selection-report.json for every gate and ATTRIBUTION.txt for source terms.\n"
    ).encode()
    files = {
        "README.md": readme,
        "ATTRIBUTION.txt": attribution,
        "sites.geojson": core._json_bytes(geojson),
        "schema.json": core._json_bytes(schema),
        "selection-report.json": core._json_bytes(report),
        "review-provenance.json": core._json_bytes(provenance),
    }
    files.update(_table_bytes(inherited_raw, delta))
    manifest = {
        "format": DRAFT_MANIFEST_FORMAT_V3
        if blind
        else DRAFT_MANIFEST_FORMAT_V2
        if corrected
        else DRAFT_MANIFEST_FORMAT_V1,
        "draft_id": f"2026-08-20-v0.18-draft-{batch.contract['batch_id']}",
        "release_status": "draft",
        "publishable_as_final": False,
        "objective_completion_claim": False,
        "base_preview_manifest_sha256": BASELINE_MANIFEST_SHA256,
        "base_preview_path": BASELINE_RELATIVE_DIR,
        "contract_path": batch.contract_path.relative_to(batch.root).as_posix(),
        "contract_sha256": batch.pins.contract_sha256,
        "counts": counts,
        "files": {
            name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            for name, raw in sorted(files.items())
        },
    }
    files["manifest.json"] = core._json_bytes(manifest)
    files["manifest.sha256"] = (
        f"{hashlib.sha256(files['manifest.json']).hexdigest()}  manifest.json\n".encode()
    )
    return files, manifest


def _validate_output(path: Path, expected: dict[str, bytes]) -> None:
    _require(
        not path.is_symlink() and path.is_dir(),
        "draft output is not a regular directory",
    )
    _require(
        {item.name for item in path.iterdir()} == set(expected),
        "draft output inventory differs",
    )
    for name, raw in expected.items():
        member = path / name
        _require(
            not member.is_symlink() and member.is_file() and member.read_bytes() == raw,
            f"draft output bytes differ: {name}",
        )


def validate_draft(
    output_dir: Path, contract_path: Path, review_pins: ReviewPins, *, root: Path = ROOT
) -> dict[str, Any]:
    """Phase two: reproduce every output byte from reviewed inputs and frozen v17."""
    batch = validate_batch(contract_path, review_pins, root=root)
    expected, manifest = _payloads(batch)
    _validate_output(Path(output_dir), expected)
    return manifest


def build_draft(
    contract_path: Path, review_pins: ReviewPins, output_dir: Path, *, root: Path = ROOT
) -> dict[str, Any]:
    """Write only a new opt-in draft after validating a complete staged artifact."""
    output_dir = Path(output_dir).absolute()
    baseline_dir = (Path(root) / BASELINE_RELATIVE_DIR).resolve()
    _require(
        not output_dir.exists() and not output_dir.is_symlink(),
        f"refusing to overwrite {output_dir}",
    )
    _require(
        not output_dir.resolve().is_relative_to(baseline_dir),
        "cannot write inside frozen baseline",
    )
    batch = validate_batch(contract_path, review_pins, root=root)
    payloads, manifest = _payloads(batch)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        for name, data in payloads.items():
            with (stage / name).open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        validate_draft(stage, contract_path, review_pins, root=root)
        _require(
            not output_dir.exists() and not output_dir.is_symlink(),
            "output appeared during draft build",
        )
        os.rename(stage, output_dir)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return manifest
