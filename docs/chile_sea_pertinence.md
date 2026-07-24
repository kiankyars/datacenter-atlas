# Chile SEA e-Pertinencia assessment lane

This isolated lane searches the Chilean Environmental Assessment Service's public e-Pertinencia listing with four exact terms, in order: `data center`, `data centre`, `datacenter`, and `centro de datos`.

The 2026-07-18 capture returned 23, zero, four, and one rows. All 28 `qidProcess` values are unique. The lane preserves every row with an explicit decision: 23 review candidates and five terminal-process exclusions. Four exclusions have substatus `Resuelta - Abandono`; one has `Resuelta - Desistida`.

Three listing rows have process state `En análisis`: PERTI-2026-7066, PERTI-2026-5962, and PERTI-2025-9340. The state describes the SEA process. It does not establish construction, operation, or a physical lifecycle milestone.

## Scope boundary

The release contains listing observations, not 28 facilities or sites. It performs no identity merge, so the unique physical site count remains null. It assigns no data-centre type or workload and infers no IT capacity, facility power, annual energy, or PUE.

The capture requested four listing responses and two SEA rights pages. It did not request the available detail endpoint. It also excluded applicant documents, attachments, comments, plans, images, and third-party material.

The upstream listing includes a holder-name field. The fetcher removes that field in memory before writing any search artifact. It retains only `qidProcess`, name, presentation and response dates, correlative ID, project type, process state and substatus, primary typology, regions, communes, and the matching query terms. Original search response bodies are not retained. The release stores only a canonical sanitized snapshot plus original byte lengths and SHA-256 hashes for audit.

## Rights boundary

SEA's terms allow copying for personal, noncommercial purposes subject to their conditions and require written permission for commercial copying or reuse. Third-party material can carry separate rights. The release marks every artifact restricted, audit-only, and ineligible for publication. It cannot feed the construction master or current coverage ledger without rights clearance. This is a source-handling decision, not legal advice.

## Reproduction

The frozen bundle is `source_assessments/chile-sea-pertinence-data-centers-2026-07-18-v1`. Directories use mode `0555`; files use mode `0444`.

Validate it without network access:

```bash
python3 scripts/validate_chile_sea_pertinence.py
```

Rebuild from the retained sanitized staging capture without network access:

```bash
python3 scripts/fetch_build_chile_sea_pertinence.py \
  --resume \
  --staging-dir .staging/chile-sea-pertinence-data-centers-2026-07-18-v1 \
  --output /path/to/new/chile-sea-pertinence-data-centers-2026-07-18-v1
```

The builder refuses to overwrite an existing output. The offline validator checks the request set, response metadata, sanitized snapshot, exact 28/23/5 arithmetic, all row decisions, inference and rights boundaries, retained hashes, manifest, sidecar, and byte-for-byte derived-file reproduction.
