# Data Center Atlas

An open dataset of data centres worldwide, from announced projects to operating facilities.
Each project links to dated evidence for its status and location.

[**Explore the atlas**](https://kiankyars.github.io/datacenter-atlas/) ·
[Download data](https://kiankyars.github.io/datacenter-atlas/data/) ·
[API](https://kiankyars.github.io/datacenter-atlas/api/)

## Data

| File | Contents |
| --- | --- |
| [sites.csv](https://kiankyars.github.io/datacenter-atlas/downloads/latest/sites.csv) | Physical sites, locations and companies |
| [projects.csv](https://kiankyars.github.io/datacenter-atlas/downloads/latest/projects.csv) | Projects and phases, statuses and reported capacity |
| [evidence.csv](https://kiankyars.github.io/datacenter-atlas/downloads/latest/evidence.csv) | Sources, dates, attribution and licence terms |

GeoJSON, SQLite, Excel and other formats are available on the
[download page](https://kiankyars.github.io/datacenter-atlas/downloads/latest/).
See the [data dictionary](https://kiankyars.github.io/datacenter-atlas/data/dictionary/)
for field definitions and the [archive](https://kiankyars.github.io/datacenter-atlas/versions/)
for reproducible snapshots and checksums.

```sh
curl -fLO https://kiankyars.github.io/datacenter-atlas/downloads/latest/sites.csv
```

Statuses describe the latest supported observation for each project. Empty fields mean unknown or
not applicable, and location precision varies. Coverage depends on public sources;
the [methodology](https://kiankyars.github.io/datacenter-atlas/methodology/) explains how records are selected and reviewed.

## Contribute

[Suggest a site](https://github.com/kiankyars/datacenter-atlas/issues/new?template=new-site.yml)
or [report a correction](https://github.com/kiankyars/datacenter-atlas/issues/new?template=correction.yml)
with a supporting source. See [CONTRIBUTING.md](CONTRIBUTING.md) for research, development and testing.

To build the website locally, run these commands from a clone with Python 3.11 or newer:

```sh
python3 scripts/build_public_site.py --output _site
python3 site/e2e/pages_server.py --directory _site
```

Open <http://127.0.0.1:8000/datacenter-atlas/>. Build and publication details are in
[docs/public_site.md](docs/public_site.md).

## Licence and citation

Code: [MIT](LICENSE). Atlas-authored data and documentation: [CC BY 4.0](DATA_LICENSE.md).
Third-party material retains its source terms, including OpenStreetMap's ODbL;
see [DATA_LICENSE.md](DATA_LICENSE.md) and each download's attribution file.
See [CITATION.cff](CITATION.cff) for citation details; include the data version you used.
