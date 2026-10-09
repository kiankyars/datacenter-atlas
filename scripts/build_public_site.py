#!/usr/bin/env python3
"""Build the static Data Center Atlas public site (HTML pages, JSON API and downloads)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(PROJECT_ROOT))

from datacenter_atlas import public_site  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="directory to write the site into")
    parser.add_argument(
        "--base-url",
        help="absolute site URL used in JSON, the feed and the sitemap (default: site/config.json base_url)",
    )
    parser.add_argument("--source-commit", help="git commit the site is built from (shown in the footer)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing output directory, but only one this builder wrote (it has a .atlas-site marker)",
    )
    parser.add_argument("--config", type=Path, help="site configuration (default: site/config.json)")
    arguments = parser.parse_args(argv)
    try:
        summary = public_site.build_site(
            arguments.output,
            root=PROJECT_ROOT,
            base_url=arguments.base_url,
            source_commit=arguments.source_commit,
            config_path=arguments.config,
            overwrite=arguments.force,
        )
    except public_site.PublicSiteError as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
