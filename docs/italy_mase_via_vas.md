# Italy MASE VIA/VAS search assessment

Release: `italy-mase-via-vas-data-centre-search-2026-07-18-v1`

This release is a bounded search assessment of the Italian Ministry of the
Environment and Energy Security environmental-assessment portal. It is not an
Italian data-centre census and does not establish construction status.

## Source and endpoint contract

The authoritative publisher is the Ministero dell'Ambiente e della Sicurezza
Energetica, Direzione Generale Valutazioni Ambientali.

- Portal: <https://va.mite.gov.it/it-IT>
- Combined VIA/VAS/AIA search: <https://va.mite.gov.it/it-IT/Ricerca/ViaVasAia>
- Portal sitemap used for rights review: <https://va.mite.gov.it/it-IT/Home/Mappa>
- Search method: `GET`
- Search parameter: `Testo`
- Pagination parameter: `pagina`
- Export parameter: `mode=export`
- Observed HTML page size: 10
- Export media type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Export disposition: `attachment; filename=Export.xlsx`

The HTML rows expose the title, proponent, object kind, procedure code, latest
procedure label, object route ID, and documentation route ID. The XLSX export
exposes four fields: title, proponent, object kind, and latest procedure label.
Every query reconciled across the paginated HTML and XLSX projection after
Unicode whitespace normalization.

The closed capture ran from `2026-07-19T02:53:58Z` through
`2026-07-19T02:55:09Z`, which was July 18 in America/Los_Angeles. It made 93
network attempts: one sitemap response, 79 HTML search pages, and 13 XLSX
exports. All 93 attempts succeeded.

## Closed query plan

The 13 phrases were declared before the bounded capture. `CED` was omitted
because its acronym ambiguity would make the result set hard to interpret.

| ID | Language | Phrase | Hits |
|---|---|---|---:|
| q01 | common English | `data center` | 68 |
| q02 | common English | `data centre` | 66 |
| q03 | common English | `datacenter` | 14 |
| q04 | common English | `data-center` | 68 |
| q05 | common English | `server farm` | 19 |
| q06 | common English | `server room` | 3 |
| q07 | common English | `computer room` | 0 |
| q08 | Italian | `centro elaborazione dati` | 134 |
| q09 | Italian | `centro di elaborazione dati` | 134 |
| q10 | Italian | `centro dati` | 130 |
| q11 | Italian | `centro di calcolo` | 64 |
| q12 | Italian | `sala server` | 18 |
| q13 | Italian | `sale server` | 17 |

The queries produced 735 memberships. Exact deduplication on portal object ID,
documentation route ID, and latest procedure code produced 186 records and
removed 549 repeated memberships.

## Classification

Classification uses the normalized portal result title only. The frozen source
definition records the exact case-insensitive regular expressions and their
evaluation order. No manual overrides are present.

| Classification | Records | Meaning in this assessment |
|---|---:|---|
| `direct_project` | 38 | The object title directly names data-centre work. |
| `ancillary_follow_up` | 5 | The title primarily names generators, wells, or water-treatment work at a data-centre site. |
| `context_only` | 0 | A data centre appears only as context for another primary work. |
| `excluded` | 143 | The title lacks the direct facility phrase required by the classification contract. |

`direct_project` is a title classification for a portal object. It does not mean
the facility is permitted, financed, under construction, complete, or operating.

The 186 exact records contain 182 `Progetto`, three `Installazione`, and one
`Programma` object. These are portal object kinds, not physical facility types.

## Rights and retention

The portal footer states `Copyright M.A.T.T.M 2017. Tutti i diritti riservati`.
The portal sitemap exposed privacy links but no portal-specific open reuse
licence. This is a conservative retention decision, not a legal conclusion.

The frozen release contains derived search metadata and response hashes. It
contains no HTML, XLSX, PDF, attachment, or decision-document response body.
Raw source redistribution is not permitted by this assessment.

The assessment artifact may be indexed as review evidence. Import into the
construction master, construction map, and current coverage ledger is explicitly
not permitted.

## Record and inference boundaries

Each observation keeps these units separate:

- `object_unit`: the portal plan, programme, project, or installation object
- `application_unit`: the latest procedure code, label, and documentation route
- `publication_units`: empty because the search row does not enumerate publications
- `decision_units`: empty because the search row does not enumerate decisions

No procedure label is converted into a physical lifecycle status. Construction
status and facility type remain null. Numeric strings in titles remain text.
Gross facility power, IT capacity, annual energy, PUE, and unique physical site
IDs remain null. Exact portal records are not merged into sites.

## Blind spots

- The release covers MASE portal objects only. Regional and local Italian
  assessment portals are outside scope.
- Attached-document full text was not searched.
- The portal provides no documented query semantics or stable sort contract.
  The observed search behavior produces many title false positives.
- The portal provides no closed publication-date filter for this combined
  search. This is a timestamped snapshot, not current coverage.
- Every search page displayed a notice that the service was temporarily
  disabled even though results and exports remained accessible.
- Title-only classification can miss a data-centre reference found only in a
  proponent field or attachment.
- Repeated regulatory objects or applications may describe one physical site.
  No physical identity resolution was attempted.
- There is no recall denominator. National, current, and global recall are all
  explicitly unclaimed.

## Validation

Run the offline validator from the `datacenter_atlas` project directory:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/validate_italy_mase_via_vas.py
```

Run the focused tests:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_italy_mase_via_vas -v
```

The release directory mode is `0555`; every release file mode is `0444`.

| Artifact | SHA-256 |
|---|---|
| source definition and embedded `definition.json` | `869ed1429b1d2662d6d5f56e80a3864e3caed85dca2e20c6d75e2334ce8e7550` |
| `capture-metadata.json` | `7bef3d06c172a6f05dd801a6c56538474a702c9edfba2a2098215d53352faef9` |
| `observations.jsonl` | `f044da5040c01d9a9870d7fa3751cf8de6bf20c319c96d2dce2265b12dc1ee0f` |
| `query-membership.jsonl` | `cfebad55a0be3bbdd7f480a25a6ef75dee242df32af92004afc340fb4b733c32` |
| `manifest.json` | `876c75f3b8818dc1034a60f791ba8dbaaea9d5b94f704151302a3b82cca940af` |
