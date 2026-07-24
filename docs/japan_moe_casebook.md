# Japan MOE data-centre decarbonization casebook lane

This lane captures defensible program and case observations from three official
Ministry of the Environment (MOE Japan) starting sources:

- landing page: <https://www.env.go.jp/earth/earth/ondanka/data-center.html>
- May 2026 casebook: <https://www.env.go.jp/content/000400242.pdf>
- site use terms: <https://www.env.go.jp/mail.html>

It is an auxiliary, review-only source lane. It is not a construction master,
a complete subsidy-award register, or a physical-site inventory.

## Reconciliation contract

The 12-page PDF says it presents only some adopted R3-R7 projects. Physical
page 3 lists nine cases. Physical pages 4-11 provide eight detailed cases.
Seven reconcile one-to-one: overview rows 1-6 and 9. Overview rows 7
(Frontend, Ehime) and 8 (Aos Field, Niigata) have no detail page. The WM case
on physical page 10 (Fukuoka Kyoto District) has no overview row and cannot be
matched to either missing case because both operator and prefecture differ.

The release therefore contains ten normalized case observations:

- 7 matched overview/detail observations
- 2 overview-only observations
- 1 detail-only observation
- unknown unique physical-site count

The two Kanden observations at Shiroi remain separate program records and are
not deduplicated into, or counted as, physical sites.

## Metric boundary

The lane retains 24 page-scoped reported metrics in four classes: renewable
generation, energy savings, renewable share, and CO2 reduction. It preserves
printed units, forecast/estimate language, self-consumption statements,
certificate inclusion, subsidy scope, and source warnings.

Important literal-source handling:

- EcoKaku's `13,889 MWh` and `1,394 MWh` figures have no printed per-year
  denominator. They are not normalized to MWh/year.
- The Kanden/IIJ page visibly prints `1.1 MWh` annual generation alongside
  `216 t-CO2/year`. Both are preserved without correction and carry an
  internal-consistency warning.
- Prologis's `448 MWh/year` generation is shared by the building and data
  centre, and the PV is explicitly self-funded outside the subsidy.
- Prologis's 100% renewable claim includes certificates.
- SB Power's figures are FY2027 forecasts; FY27 is not R7/FY2025.

No metric is converted into total electricity consumption. No observation
supplies or infers IT load, utility capacity, PUE, physical data-centre type,
construction status, operating status, address, coordinates, or commissioning
date. Program labels such as new-build support, retrofit support, and container
support describe subsidized work categories only.

## Rights and retained content

The MOE terms state that PDL1.0 applies unless otherwise noted, require source
attribution, and require a separate editing/processing disclosure. Processed
content must not be represented as untouched government content. The MOE logo
is outside this lane's reuse scope, and individual-law constraints may apply.

The casebook credits operator submissions, interviews, municipal material,
public information, and NRI compilation. This lane makes no legal conclusion
and does not claim third-party clearance. It redistributes no PDF, HTML, page
image, photograph, diagram, logo, or third-party source body. Only a factual,
page-scoped structured transcription is pinned, with MOE attribution and a
DataCenter Atlas processing disclosure.

## Direct HTTP accounting

The bounded audit made exactly three direct GET attempts, in terms-first order,
with no redirects and request starts at least 3.2 seconds apart. The cap was 12.
All requests went to the three approved `www.env.go.jp` URLs; third-party
requests were zero. Browser-proxy research was separate, and its origin request,
cache, and redirect count is unknown and excluded from direct-request arithmetic.
Raw response bodies and render intermediates were deleted after the structured
source artifact was pinned.

## Reproduction and validation

Build from the frozen local source artifact, with no network access:

```sh
python3 scripts/build_japan_moe_casebook.py
```

Validate the frozen release offline:

```sh
python3 scripts/validate_japan_moe_casebook.py
```

Writable draft copies are rejected by default. A draft copy can be checked
explicitly without weakening semantic or hash validation:

```sh
python3 scripts/validate_japan_moe_casebook.py \
  --release /path/to/draft \
  --allow-writable-release
```
