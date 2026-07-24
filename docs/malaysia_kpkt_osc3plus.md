# Malaysia KPKT OSC 3 Plus discovery assessment

## Decision

The official source assessed here is KPKT's
[OSC 3 Plus](https://osc3plus.kpkt.gov.my/) municipal planning service. Its
public PBT pages expose calendar and meeting surfaces that could support a
bounded data-centre discovery lane. This v1 release stops before those surfaces
because the audit did not establish an affirmative right to capture and
redistribute source records.

The 2026-07-18 local-date audit requested only six rights/access surfaces: the
service root, its robots file, and four linked policy endpoints. The root and
robots file returned HTTP 200. The four policy endpoints returned HTTP 500.
The root asserted copyright, and the robots policy did not disallow generic
access. Robots controls crawling; it is not treated as a reuse licence. The
release makes no legal conclusion and requires source-specific clarification
before the first PBT or meeting request.

No response body, HTML, footer excerpt, policy text, meeting item, applicant,
contact, personal data, or derived source row is retained. The audit inventory
contains only URL, method, HTTP status, content type, byte count, response date,
and SHA-256 for each controlled request.

## Closed future traversal contract

The exact PBT-page allowlist is:

- [MBJB](https://osc3plus.kpkt.gov.my/pbt/MBJB), Majlis Bandaraya Johor Bahru;
- [MBIP](https://osc3plus.kpkt.gov.my/pbt/MBIP), Majlis Bandaraya Iskandar
  Puteri;
- [MPKu](https://osc3plus.kpkt.gov.my/pbt/MPKu), Majlis Perbandaran Kulai;
- [MBPG](https://osc3plus.kpkt.gov.my/pbt/MBPG), Majlis Bandaraya Pasir Gudang;
  and
- [MPSep](https://osc3plus.kpkt.gov.my/pbt/MPSep), Majlis Perbandaran Sepang.

This is a selected-PBT scope, not a complete Johor, Selangor, or Malaysia
inventory. The explicit jurisdiction mapping is MBJB = Johor Bahru, Johor;
MBIP = Iskandar Puteri, Johor; MPKu = Kulai, Johor; MBPG = Pasir Gudang,
Johor; and MPSep = Sepang, Selangor. MPSep is the Cyberjaya comparator. It is
not Kuala Lumpur city and cannot substitute for DBKL coverage.

If KPKT later affirms the required reuse scope, the collector may request each
allowlisted page once and inspect only inline current-year calendar events from
2026-01-01 through 2026-07-18 inclusive. It may follow a meeting link only when
the link is discovered from an allowlisted page, remains on the official OSC 3
Plus origin, and matches `/takwim/meeting/{positive integer}`. Integer guessing
or scanning is forbidden.

The exact casefolded literals are:

- `pusat data`;
- `data centre`;
- `data center`; and
- `pusat ibu sawat komputer`.

The future observation unit is one agenda presentation item, keyed only by
exact `(meeting_id, presentation_ordinal)`. The retrieval ceiling is five PBT
page requests, 100 discovered meeting pages per PBT, and 500 meeting-page
requests total. Requests must be sequential and at least five seconds apart.
Every response must be hash-bound. Any error or ceiling stops the run and keeps
all completeness counts null.

## Coverage and unit boundaries

The run made zero PBT calendar requests and zero meeting-page requests. It does
not claim completeness for Malaysia, Johor, or Selangor. Because source
traversal never occurred, these counts remain null rather than zero:

- results;
- calendar events;
- meeting pages;
- agenda presentation items;
- classification categories;
- projects;
- sites; and
- source metric statements.

Exact retained counts are zero for agenda observations, classification rows,
derived rows, and metric rows.

An agenda item is an administrative observation, not an atlas project or
physical site. A calendar or meeting status does not establish construction
start, completion, or operation. The release infers no data-centre type,
operator, IT capacity, gross facility power, backup capacity, PUE, annual
energy consumption, or physical lifecycle.

## DBKL gap

Kuala Lumpur city remains explicitly uncovered. The separate official
[DBKL OSC](https://osc.dbkl.gov.my/) and
[public dashboard](https://oscdashboardawam.dbkl.gov.my/) were not requested in
this bounded KPKT audit, so no DBKL result count is asserted. The gap must be
addressed by a separately authorized assessment; Cyberjaya cannot fill it.

## Downstream and validation

This metadata-only assessment cannot feed the construction master, map, or
current-coverage ledger. The release directory is mode `0555`; every file is
mode `0444`. Validate and reproduce it entirely offline:

```bash
cd datacenter_atlas
python3 scripts/validate_malaysia_kpkt_osc3plus.py
python3 -m unittest tests.test_malaysia_kpkt_osc3plus
python3 scripts/build_malaysia_kpkt_osc3plus.py \
  --output /tmp/malaysia-kpkt-release \
  --definition /tmp/malaysia-kpkt-definition.json
```
