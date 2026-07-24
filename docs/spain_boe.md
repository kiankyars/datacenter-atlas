# Spain BOE exact-phrase publication lane

This lane searches the official *Boletín Oficial del Estado* and produces a review-only publication assessment. It does not produce sites or current-construction records.

## Query boundary

The closed query uses six exact phrases: `centro de datos`, `centros de datos`, `centro de procesamiento de datos`, `centro de proceso de datos`, `data center`, and `datacenter`. It searches BOE full text (`DOC`) from 2016-01-01 through 2026-07-18, includes sections I, III, and V, requests up to 2,000 hits, and sorts by publication date, origin, and reference. Sections II, IV, and Constitutional Court publications are outside this lane.

The six result counts are 66, 163, 58, 323, 38, and 29. Exact BOE-ID deduplication yields 658 publications. That bounded union is fully classified, but it is not comprehensive for Spain: other terminology, other official gazettes, planning portals, grid registries, operator disclosures, and imagery remain separate sources.

## Classification and inference

`direct_project_build_expansion_candidate` means that the official publication itself describes a facility build, conversion, expansion, or professional procurement directly supporting such work. `ancillary_or_administrative_context` covers related utilities, equipment, communications, migration, funding categories, audits, budgets, laws, and policy. Everything else is excluded with a retained category, while its title is removed.

The BOE publication is always the row unit. A tender and its formalised contract remain two rows. A grant resolution containing several projects has a `project_units` array. No project or publication is merged into a facility, no site count is inferred, and no BOE process state becomes a physical lifecycle state.

Power, energy, water, and electrical facts require a metric, unit, numeric value, and explicit scope. A facility-power statement is not relabelled as IT power, and a grid application is not relabelled as measured consumption. PUE, IT power, annual energy, physical lifecycle, and unique-site count remain null unless another source establishes them.

## Rights, retention, and reproduction

The BOE reuse notice permits reuse with attribution, a source link, preservation of meaning and update metadata, identification of modifications, and no implied sponsorship. Personal-data law continues to apply. The release therefore retains sanitized publication metadata and paraphrased project evidence, but not raw query pages, detail XML, PDFs, excluded titles, names, signatures, addresses, tax identifiers, phone numbers, or email addresses.

The builder consumes a bounded, reviewed capture and records response hashes without retaining search/detail bodies:

```bash
python3 scripts/fetch_build_spain_boe.py
```

The frozen release validates offline:

```bash
python3 scripts/validate_spain_boe.py
```
