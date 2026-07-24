# Explicit v71 satellite-change tranche

This adapter runs only the eleven queue IDs copied into the immutable
`2026-07-21-open-seed-v71-active-explicit-001` catalog selection receipt. The
other 87 represented active-construction jobs remain unselected and pending;
they are not runnable through this adapter.

The implementation pins the exact generic change carrier, explicit catalog
validator, queue, catalog manifest, and selection receipt. It loads the
generic carrier in an isolated namespace, retains its offline validation and
numerical processor, and changes only two execution boundaries: catalog input
comes from the explicit-v1 validator, and each finished job directory is
published with an atomic no-replace rename. A running checkpoint with an
uncheckpointed final directory is rejected rather than adopted. Every job has
one lifetime attempt.

Run from `datacenter_atlas/` with the pinned numerical runtime:

```sh
uv run --python 3.12 \
  --with numpy==2.5.1 --with pillow==12.3.0 --with rasterio==1.5.0 \
  python scripts/run_satellite_change_batch_explicit_v1.py
```

Offline validation uses the same pinned inputs and makes no network requests:

```sh
uv run --python 3.12 \
  --with numpy==2.5.1 --with pillow==12.3.0 --with rasterio==1.5.0 \
  python scripts/run_satellite_change_batch_explicit_v1.py --validate-only
```

The outputs are machine-generated visible-change proposals requiring analyst
review. They do not identify a data centre or infer identity, operator, site
type, construction or operating status, lifecycle, capacity, PUE, workload,
power, or energy. They do not mutate the construction master, map, timeline,
identity accounting, capacity ledger, or coverage claims.
