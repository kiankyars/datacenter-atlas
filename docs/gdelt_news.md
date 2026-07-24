# GDELT bulk-news review lane

This lane discovers articles for analyst review. It does not create facilities, lifecycle
observations, construction projects, capacity estimates, or power and energy claims. A candidate
means only that one GDELT document matched both a data-centre term and a development term in the
same language-specific lexical screen.

## Pinned source

The pilot uses the one-minute GDELT Web NGrams example snapshot `20260630201600` documented by
[The GDELT Project](https://blog.gdeltproject.org/using-the-new-web-ngrams-dataset-to-find-relevant-coverage/).
GDELT describes this as a non-consumptive, per-document quadgram dataset for finding relevant
coverage without distributing article full text. Each minute is represented by two files:

- `20260630201600.ngrams.txt.gz`, containing document ID, quadgram, and count rows;
- `20260630201600.toc.json.gz`, containing the corresponding article URL, title, timestamp,
  language, and image URL metadata.

The fetch specification pins each Google Cloud Storage object generation, compressed byte count,
and MD5. Requests use the generation-qualified URL, identity transfer encoding, a transparent
User-Agent, and at least 1.1 seconds between request starts. The default run budget is two requests.
Partial files are resumed with a validated HTTP range; generation, ETag, final byte count, MD5, and
SHA-256 must all reconcile before publication.

```sh
python3 scripts/fetch_gdelt_news.py \
  --output source_cache/gdelt-web-ngrams-20260630201600 \
  --max-requests 2
```

The completed source directory has an exact three-file inventory: the two original gzip objects
and canonical `manifest.json`. A completed rerun rehashes the files and performs no network request.

## Candidate extraction

The versioned seed lexicon covers 23 GDELT language codes. It is deliberately small and is not a
claim of linguistic completeness. A candidate requires at least one subject term and one
development term across its normalized title and quadgrams. Unsupported languages are counted and
left unmatched. The extractor does not fetch article URLs or bodies.

For each match, `candidates.jsonl` retains the article URL, timestamp, language, title, publisher
domain, matched terms, and at most 40 lexicographically smallest matching quadgrams. A two-letter
publisher-domain ccTLD may be retained only as a publisher-domain hint; it is never article or
facility geography. No location is inferred from the article text.

```sh
python3 scripts/extract_gdelt_news.py \
  --input source_cache/gdelt-web-ngrams-20260630201600 \
  --output source_cache/gdelt-news-review-20260630201600 \
  --generated-at <explicit-timezone-aware-timestamp>
```

The candidate bundle is directory-atomically published with canonical JSONL, canonical
`manifest.json`, and `manifest.sha256`. Validation checks the exact file set, hashes, record order,
typed fields, query contract, source pins, URL-derived publisher hints, and count reconciliation.
The output directory is immutable: a rerun must use a new path.

Candidates remain outside confirmed releases and require source-article review plus independent
corroboration before any atlas claim. Syndicated copies also remain one evidence family unless a
report adds independent information.

## Pinned pilot result

The `20260630201600` pilot read 1,977 TOC documents and 1,063,647 NGrams rows. The lexical screen
found 48 documents with subject terms and 797 with development terms; requiring both produced 14
review candidates at 14 distinct article URLs. Some candidates are syndicated copies or obvious
lexical false positives, so these counts measure only the review queue, not facilities or evidence.

The separate manual-triage bundle reviewed all 14 rows. It retained three project-or-policy leads
for authoritative source follow-up and rejected eleven context-only, non-facility, syndicated, or
lexical-noise rows. The retained San Marcos item concerns a rejected land-use proposal and must not
be represented as simply proposed; the Toledo item still requires permit, land, power, buyer, and
lifecycle verification; the YPF item is exploratory strategy without a verified committed site.
No atlas claim was created. The triage manifest SHA-256 is
`c5c2d900ec72397f676cf26247bf23fb60607eb015bc2e610cf8b52cf50752d0`.

The immutable source manifest SHA-256 is
`d495bf32c8338340058c28f668783a1ed5bd19169f119f26722c0c8d54e072f7`. The candidate JSONL SHA-256
is `f01e4ff0a3740efa181170fa0116ba7f4ddc1359fd693606c2bc44e691096882`, and the candidate manifest
SHA-256 is `a175424f6099dfd0567cdcccc7facb5ca47063af33fb6890735414b76a474f22`.

## Terms and attribution

[GDELT's terms](https://www.gdeltproject.org/about.html#termsofuse) permit unlimited and
unrestricted use of its datasets and require use or redistribution to cite and link to The GDELT
Project. Source and candidate manifests therefore retain: `Data from The GDELT Project
(https://www.gdeltproject.org/)`. This lane stores no article body.
