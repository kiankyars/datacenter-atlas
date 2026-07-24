# Netherlands KOOP official-publications assessment

This lane is a frozen, conservative assessment of one official Netherlands
publications query. It is a permit-publication review queue, not a facility
inventory or a claim of complete Netherlands coverage.

## Bounded query and snapshot

The release
`source_assessments/netherlands-koop-official-publications-2026-07-18-v1/`
retains one KOOP SRU 2.0 `searchRetrieve` response from
`https://repository.overheid.nl/sru`, retrieved at
`2026-07-19T00:44:23Z`. The exact CQL query is:

```text
c.product-area=="officielepublicaties" AND dt.title any "datacenter datacentrum" AND dt.type=="omgevingsvergunning" AND dt.available>="2026-01-01"
```

The request uses the `gzd` record schema, `startRecord=1`, and
`maximumRecords=100`. KOOP returned `numberOfRecords=20` with result-count
precision `estimate`, all 20 records, and no next-record position. The raw SRU
response is 106,609 bytes with SHA-256
`e4bd38159c1988d8ea8876b188d3c81ee519cb4581ac4e9b78f73e64e4483abb`.

The query is intentionally narrow. It can miss records outside 2026, records
whose titles use other vocabulary, non-environmental-permit publications, and
projects not yet represented in official publications. A future refresh must
use a new release ID rather than silently changing this snapshot.

## Record-by-record review

Every returned record is retained. Thirteen are direct project, build,
expansion, phase, or permit-modification review candidates; seven are excluded
from that direct lane as ancillary or contextual records.

| Official identifier | Review label | Publication process stage | Classification |
| --- | --- | --- | --- |
| `gmb-2026-31793` | Ecoracks EOS battery systems | `application_received` | Ancillary/context exclusion |
| `gmb-2026-334667` | Ecoracks EOS battery systems | `decision_on_application` | Ancillary/context exclusion |
| `prb-2026-6693` | Equinix AM6 energy generation | `application_received` | Ancillary/context exclusion |
| `prb-2026-1555` | Linieweg building B data-centre permit | `permit_granted` | Direct review candidate |
| `prb-2026-5306` | AMS11 phase 1 | `permit_granted` | Direct review candidate |
| `gmb-2026-175789` | Boerhaaveweg 10 data-centre application | `decision_period_extended` | Direct review candidate |
| `gmb-2026-334666` | Cateringweg 5 existing data-centre legalization | `application_received` | Ancillary/context exclusion |
| `gmb-2026-135103` | Boerhaaveweg 10 data-centre application | `application_received` | Direct review candidate |
| `prb-2026-1810` | Archangelkade Serverfarm phase 3 | `application_received` | Direct review candidate |
| `prb-2026-11665` | Koolhovenlaan 142 data-centre project | `permit_granted` | Direct review candidate |
| `prb-2026-2233` | Goodman De Liede data-centre permit modification | `permit_modified` | Direct review candidate |
| `prb-2026-11305` | QTS EEMS02 boundary modification | `final_permit_decision` | Direct review candidate |
| `prb-2026-1413` | Archangelkade Serverfarm phase 3 | `application_received` | Direct review candidate |
| `prb-2026-10866` | AMS11 phase 1 | `permit_granted` | Direct review candidate |
| `prb-2026-11319` | Equinix AM9 and AM10 | `draft_decision_open_for_inspection` | Direct review candidate |
| `prb-2026-11662` | Koolhovenlaan 142 data-centre project | `permit_granted` | Direct review candidate |
| `gmb-2026-299345` | De Kwakel medium-voltage connection | `application_received` | Ancillary/context exclusion |
| `gmb-2026-162314` | De Kwakel medium-voltage connection | `application_rejected` | Ancillary/context exclusion |
| `gmb-2026-20613` | De Kwakel medium-voltage connection | `application_received` | Ancillary/context exclusion |
| `prb-2026-11613` | Koolhovenlaan 142 data-centre project | `permit_granted` | Direct review candidate |

The seven exclusions are two Ecoracks battery-system publications, one Equinix
AM6 energy-generation application, three De Kwakel medium-voltage-connection
publications, and one application to legalize an existing data centre. Eight
selected official XML details resolve those boundaries and the QTS record,
whose SRU metadata has no abstract. No other full publication manifestation
was fetched.

## Metadata, geography, and evidence boundaries

Each JSONL observation preserves the structured original metadata, all original
metadata leaf values and attributes, all enriched metadata leaf values and
attributes, six manifestation URLs, record position, record timestamp, raw
ETRS89 location-point strings, parsed ETRS89 points, source geometry strings,
and SHA-256 lineage. All 20 records have source geometry; 16 have at least one
ETRS89 location point. Missing values remain missing.

Publication process stages are process evidence only. A received, granted,
modified, draft, or final permit publication does not prove that construction
started, completed, or became operational. Every observation therefore remains
review-only, is not auto-merged, does not count a unique site, and has no
promoted lifecycle status, data-centre type, power, IT capacity, annual energy,
PUE, workload, construction, or operation claim.

The AM6 phrase
`grootschalig opwekken energie (50 MW of meer) t.b.v. datacentrum Equinix AM6`
is preserved as one untyped contextual statement. The `50 MW` threshold is not
interpreted as gross facility power, IT load, or energy consumption.

Six obvious same-case, same-project, or multi-phase sequences attach 14 records
to advisory groups. The relationships have zero accepted identities, zero
automatic merges, and no unique physical-site count.

## Rights and retrieval scope

The official Data Overheid catalog labels the collection `CC-0 (1.0)`. KOOP's
copyright page says website text is generally under CC0 1.0 unless an express
copyright notice says otherwise, while images and videos generally cannot be
reused. The eight selected XML details contain no explicit copyright marker.
The release makes no reuse claim for images or video and does not fetch or
redistribute the publications' PDF, ODT, HTML, or metadata manifestations.

The official SRU 2.0 guide PDF is retained solely as collection-methodology
evidence; it is not a fetched publication attachment. All 12 bounded HTTPS
requests are recorded with purpose, timestamps, pacing policy, attempts,
retries, response metadata, byte counts, effective URLs, and SHA-256. Every
request succeeded on its first attempt; offline validation performs zero
network requests.

## Reproduction and validation

The source definition is 22,302 bytes with SHA-256
`ee23b0cd9b7e1584b48579f79a4451bf4de1b7392a1c58d13280cb7dbef78847`.
The frozen bundle contains 24 files, retains 1,670,751 raw bytes, and has
manifest SHA-256
`2fc151a0088f4d03cba8985fb45552400236518cd9022672d49280ab9d4d9cd2`.
Selected derived checkpoints are:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `assessment.json` | 13,176 | `2cdf1f78b80173c369634936742e8ce9464d10dda7a8d791f770bc65095b0a1f` |
| `source-inventory.json` | 4,254 | `55dc8ad32746d18ffc52a68138e44c3be6660872c1b838616f1f940c0bf3e9a6` |
| `observations.jsonl` | 245,239 | `888ea15acf3d169c41d3f0b4e3c19f3e42056a6b74f9f03987d321dabe8e13b2` |
| `observations.csv` | 48,402 | `848348bc0c48a6cbddf39f41c36f42bf457321ba8349052d215671abcb33bf67` |
| `advisory-relationships.json` | 2,930 | `28ff4fda7ba819e0782e22f1760f9ac26f911208cbaff74650abc7f3b3ac7a00` |
| `request-log.jsonl` | 11,052 | `6756906326e8a7513e78dd765ad78acc153b1383e5ff275fff24f4cf84fa01f3` |

From `datacenter_atlas/`, validate the frozen release and reproduce every
derived byte without network access:

```sh
python3 scripts/fetch_build_netherlands_koop.py --validate-only
```

The builder refuses an existing output. The validator checks the closed file
set, source definition, raw and request-log checkpoints, canonical
JSON and JSONL, SRU query/count/order, metadata manifestations, selected detail
markers, rights evidence, classification arithmetic, no-promotion boundaries,
manifest roles and license scopes, and byte-for-byte offline re-derivation.
