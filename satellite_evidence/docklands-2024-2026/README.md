# Ada Docklands Sentinel-2 change evidence

This bounded review bundle compares Sentinel-2 L2A imagery over the Ada Infrastructure Docklands
campus parcel in West Silvertown, London. It is supporting physical-change evidence for a known
project, not discovery of an unknown site and not an independent identity, lifecycle, power, or
operating-status claim.

The parcel was targeted from the official planning address (the former paint factory and Central
Thameside West, North Woolwich Road, E16 2AB), Ada's construction disclosure, and OpenStreetMap way
`988357327`, which was tagged `construction=data_center` with a 2026-04-06 check date. OpenStreetMap
geometry is ODbL-1.0 data and requires `© OpenStreetMap contributors` attribution.

The catalog manifest preserves the exact Earth Search responses and SHA-256 hashes. The selected
season-matched scenes are `S2B_30UXC_20240626_0_L2A` and `S2C_30UXC_20260624_0_L2A`. The site-cropped
comparison has 100% mutually valid pixels and proposes three connected optical-change components
of at least 1,000 m², totaling 9,100 m². These are changed spectral pixels, not floor area.

Files:

- `catalog/manifest.json`: requests, normalized results, selected scene IDs, rights, and hashes.
- `catalog/*-response.json`: exact saved STAC responses.
- `change/comparison.png`: before, after, and threshold overlay.
- `change/change-proposals.geojson`: review-only connected change components.
- `change/report.json`: algorithm version, radiometry, thresholds, limitations, metrics, and hashes.

The first automatic current-scene choice passed the scene-wide cloud threshold but was cloudy over
this small parcel. That run was rejected. The checked bundle narrows the query to 5% scene-wide
cloud cover, uses the deterministic selected pair above, and records the resulting local valid-pixel
fraction. Production selection must score cloud and shadow over the AOI, not only over the full
Sentinel tile.
