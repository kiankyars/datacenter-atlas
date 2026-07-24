# NSW Major Projects Data Storage lane

This lane preserves planning-process observations from the NSW Department of Planning, Housing and Infrastructure's Major Projects register, filtered by the portal's exact `Data Storage` development type. It covers state-significant applications and modifications only. It does not cover ordinary local development applications and is not a complete NSW or Australian data-centre inventory.

The frozen 2026-07-18 Los Angeles-date snapshot contains 44 list cards across five pages: 35 base applications and nine modifications. Detail pages were retrieved only for the 22 rows whose exact list-stage string was one of `Assessment`, `Exhibition`, `Prepare EIS`, or `Response to Submissions`. This subset contains 19 base applications and three modifications. “Active” in this module means only that the portal workflow stage matched this nonterminal set; it never means physically under construction or operating.

Run a new bounded capture and build with a new release identifier rather than overwriting the frozen bundle:

```bash
python scripts/fetch_build_nsw_major_projects.py \
  --staging-dir /private/tmp/nsw-major-projects-staging \
  --min-request-interval 1.05 \
  --max-network-requests 50
```

The fetcher reads page zero's displayed count, derives the number of nine-card pages, paces request starts by at least one second, retries retryable failures with bounded exponential backoff, and refuses to exceed 50 attempts. It fetches no attachments or document bodies.

Validate the repository snapshot without network access:

```bash
python scripts/validate_nsw_major_projects.py
```

The release retains exact list/detail HTML and response hashes for audit. Detail HTML can contain submissions and other mixed-rights page material, so raw HTML is not redistribution-eligible. Derived list/detail observations include portal metadata, descriptions, milestones, exact portal point coordinates, and generic attachment-category presence. No attached EIS, plan, photograph, map, submission document, or applicant document is fetched.

The Department's copyright statement says Department material is CC BY 4.0 unless otherwise stated, with attribution. It excludes third-party intellectual property—including photographs, illustrations, drawings, plans, artwork, and maps—which may not be expressly identified, as well as government marks, judgments, and legislation. Attribution for derived Department material is recorded in `ATTRIBUTION.txt`.

Modifications remain separate observations. Their parsed `SSD-…-Mod-…` relationship to a base case is advisory and never authorizes identity fusion. List and detail LGA text are both preserved; two active rows differ between those page locations. Portal coordinates are points, not parcel or facility boundaries.

MW, GW, and MVA phrases are preserved exactly with the full Department-description context. Their metric type remains null: the lane does not interpret them as IT load, facility capacity, grid connection, gross power, consumption, or annual energy. The lane also publishes no construction verification, operating model, workload, PUE, facility identity, lifecycle promotion, or unique-site count.
