# Poland GDOŚ/SIOS/Ekoportal source lane

The official GDOŚ register page sends GDOŚ and regional-directorate document
cards published from 1 June 2025 to the SIOS public search and older GDOŚ cards
to an Ekoportal archive. This scope does not cover every Polish environmental
or planning authority.

The SIOS form is a public `GET /search/common` interface. It exposes a
`keywords` field, date and location filters, document type and topic filters,
and PDF/XLS export icons. It documents no API, exact-phrase behavior,
pagination parameter, page size, stable sort, or stateless export contract.

The lane is frozen as a metadata-only blocker because:

- `https://system.sios.pl/robots.txt` says `User-agent: *` and `Disallow: /`;
- no common-search result-level reuse scope across all publishers was found;
- the official GDOŚ/RDOŚ register split is not national all-authority coverage;
- the separate statutory national GDOŚ EIA database is officially blocked
  outside Poland; and
- an administrative card, application, decision, EIA proceeding, or
  publication is not proof of physical construction.

The future literal plan contains `centrum danych`, `centra danych`, `data
center`, and `serwerownia`, but none was submitted. Source-side exact matching
is undocumented, so a future authorized run must apply a local exact-literal
postfilter. `serwerownia` is context-sensitive and can never auto-promote a
project.

The controlled audit made 10 direct-origin request attempts, paced at least
3.2 seconds between request starts, against a cap of 40. Eight returned
responses and two national-EIA probes timed out. Result, export, detail, and
document requests were all zero. Browser-proxy research is disclosed
separately because its exact origin request count is unavailable.

Validate offline from the `datacenter_atlas` directory:

```bash
python3 scripts/validate_poland_gdos_sios_ekoportal.py
```
