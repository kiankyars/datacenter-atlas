# PJM large-load and data-center materials

PJM is a useful grid-demand calibration source, not a facility census. The pinned assessment is
`source_assessments/pjm-large-load-2026-07-18-v1/`. It contains metadata and semantic controls
only: no source PDFs or workbooks, numeric calibration series, or facility leads are retained.
The manifest SHA-256 is
`8347df3e3429c3c8d9c7ef1be0a7a86187a71f8380637ee72bcf21aa08ff359f`;
the assessment and calibration SHA-256 values are
`c3c70505cd3290fe3683b173d6c6b810276f7b3aeb2a72e9fee1c1350d56a100` and
`f63cc359e6424aa63566e534fe44097aa25bd1f121ae18079952e8e95331393f`.

## Rights boundary

PJM's [Legal & Privacy notice](https://www.pjm.com/about-pjm/legal.aspx) says access to the
website does not confer a license or ownership interest in its form or content and reserves those
rights. The footer is “All rights reserved.” No affirmative redistribution or derivative-data
license was found for the static Load Analysis Subcommittee and load-forecast materials.

Some documents are marked “Public” or “For Public Use.” Those audience labels are not treated as
a reuse license because the legal notice controls website access. The Atlas therefore fails
closed: no raw cache, republished numeric tables, or extracted project rows without written PJM
permission or another independently sufficient rights basis. This is a source-governance decision,
not legal advice. It covers static `pjm.com` materials only and does not assess or authorize Data
Miner use.

## Assessed corpus

The assessment hashes 42 current official-host retrievals made at
`2026-07-18T21:51:15Z`: 31 PDFs, seven XLSX workbooks, and four HTML responses. The bounded set
includes:

- all 13 large-load request presentations and the informational request workbook from the
  [September 16, 2025 LAS meeting](https://www.pjm.com/committees-and-groups/subcommittees/las.aspx);
- PJM's [November 24, 2025 request summary](https://www.pjm.com/-/media/DotCom/committees-groups/subcommittees/las/2025/20251124/20251124-item-03---large-load-adjustment-requests-summary.pdf);
- the [2026 Long-Term Load Forecast presentation](https://www.pjm.com/-/media/DotCom/committees-groups/subcommittees/las/2026/20260123/20260123-item-03---pjm-2026-long-term-load-forecast---presentation.pdf);
- the [2026 Load Report](https://www.pjm.com/-/media/DotCom/library/reports-notices/load-forecast/2026-load-report.pdf),
  its tables/data/adjustment and accuracy workbooks, and the
  [2026 supplement](https://www.pjm.com/-/media/DotCom/planning/res-adeq/load-forecast/load-forecast-supplement-2026.pdf); and
- all 13 EDC/LSE supporting-methodology documents linked from PJM's
  [Load Forecast Development Process](https://www.pjm.com/planning/resource-adequacy-planning/load-forecast-dev-process).

Twenty-six of the artifacts are stakeholder-authored submissions hosted by PJM. PJM's legal
notice says third-party postings may not represent PJM's position, so those documents are primary
only for the submitting utility's claims. PJM hosting is not PJM endorsement.

## Row granularity

The 2025 request workbook is keyed by zone, EDC/LSE area, and year. The PJM summary presents RTO,
zone, EDC/LSE, and year aggregates. The 2026 report suite similarly exposes RTO, LDA, zone,
EDC/LSE, and time aggregates. None is a facility table.

Three 2025 stakeholder presentations contain anonymous project-level detail: FirstEnergy reports
41 included projects, AES Ohio lists eight numbered data-center requests, and Duquesne describes
one unidentified large-load request. The 2026 FirstEnergy supporting document expands 41
anonymous rows, including 33 labeled data center and eight other load types, with fields such as
ZIP code, source-scored maturity, MW, and projected in-service date. These are row occurrences,
not 91 unique sites: cross-document overlap is unresolved, no canonical facility names or
coordinates are supplied, and the Duquesne load type is unspecified.

The assessment consequently emits zero facility rows and leaves unique facility count `null`.
Anonymous customer numbers, ZIP codes, utility tracking numbers, and projected dates must not be
treated as canonical site identity or construction evidence.

## Quantity and status semantics

The documents use several non-equivalent quantities:

- requested capacity in MW is a customer/utility facility-size request in load terms;
- requested or contracted MVA is apparent power and cannot be converted to MW without an explicit
  power factor;
- requested demand MW may already include utility-specific ramp, utilization, or probability
  assumptions;
- contracted demand or capacity records a service or financial commitment, not actual use;
- a PJM forecast-adjustment MW value is modeled forecast inclusion, not requested capacity or
  metered load; and
- historical metered MW/MWh appears only as EDC/LSE or data-center-fleet aggregates in this
  corpus and cannot be assigned to a facility.

PJM's supplement defines “Firm” and “Non-Firm” as forecast-certainty classes. “Firm” is based on
an Electric Service Obligation or Construction Commitment. A Construction Commitment concerns a
utility obligation or capital-plan indication for grid facilities; it does not verify physical
construction of the customer data center. Likewise, a projected in-service date is not
commissioning evidence.

Peak MW cannot be converted to annual MWh without an explicit time series or load-factor model,
and a modeled load factor is not metered consumption. No PJM quantity in this assessment is
promoted to an Atlas facility-power or energy field.

## Offline validation

The validator performs no network requests:

```sh
python3 scripts/validate_pjm_large_load_assessment.py
```

It pins the 42 official URLs, response hashes and byte counts, fail-closed rights decision,
document-level granularity, quantity/status distinctions, zero emitted series, and zero emitted
facility leads.
