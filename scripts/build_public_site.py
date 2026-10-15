#!/usr/bin/env python3
"""Build the static Data Center Atlas public site (HTML pages, JSON API and downloads)."""

from __future__ import annotations

import argparse
import csv
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
    parser.add_argument("--output", type=Path, help="directory to write the site into")
    parser.add_argument("--release-assets", type=Path, help="separate release staging directory (default: <output>-release-assets)")
    parser.add_argument("--write-release-inventory", type=Path, help="seal current assets to a new inventory file instead of building the site")
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
    if not arguments.output and not arguments.write_release_inventory:
        parser.error("--output or --write-release-inventory is required")
    if arguments.write_release_inventory and (arguments.output or arguments.release_assets):
        parser.error("--write-release-inventory cannot be combined with output directories")
    try:
        if arguments.write_release_inventory:
            inventory = public_site.write_release_inventory(
                arguments.write_release_inventory, root=PROJECT_ROOT,
                config_path=arguments.config, base_url=arguments.base_url,
            )
            print(json.dumps({"inventory": str(arguments.write_release_inventory), "dataset": inventory["dataset_id"],
                              "files": len(inventory["files"])}, indent=2))
            return 0
        summary = public_site.build_site(
            arguments.output,
            root=PROJECT_ROOT,
            base_url=arguments.base_url,
            source_commit=arguments.source_commit,
            config_path=arguments.config,
            overwrite=arguments.force,
            release_assets_dir=arguments.release_assets,
        )
    except public_site.PublicSiteError as error:
        parser.exit(1, f"error: {error}\n")
    except (UnicodeError, csv.Error) as error:  # inputs the builder could not decode or parse
        parser.exit(1, f"error: unreadable input: {error}\n")
    except OSError as error:  # an unreadable input or an unwritable output directory
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
