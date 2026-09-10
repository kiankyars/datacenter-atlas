#!/usr/bin/env python3
"""Build or validate a reviewed opt-in expansion draft, not the public core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas import (  # noqa: E402
    expansion_200_eighteenth_reviewed,
    expansion_200_eighth_reviewed,
    expansion_200_eleventh_reviewed,
    expansion_200_fifteenth_reviewed,
    expansion_200_fifth_reviewed,
    expansion_200_fourteenth_reviewed,
    expansion_200_fourth_reviewed,
    expansion_200_initial_five,
    expansion_200_initial_three,
    expansion_200_nineteenth_reviewed,
    expansion_200_ninth_reviewed,
    expansion_200_second_reviewed,
    expansion_200_seventeenth_reviewed,
    expansion_200_seventh_reviewed,
    expansion_200_sixteenth_reviewed,
    expansion_200_sixth_reviewed,
    expansion_200_tenth_reviewed,
    expansion_200_third_reviewed,
    expansion_200_thirteenth_reviewed,
    expansion_200_thirtieth_reviewed,
    expansion_200_thirty_first_reviewed,
    expansion_200_thirty_second_reviewed,
    expansion_200_thirty_third_reviewed,
    expansion_200_twelfth_reviewed,
    expansion_200_twentieth_reviewed,
    expansion_200_twenty_eighth_reviewed,
    expansion_200_twenty_first_reviewed,
    expansion_200_twenty_fifth_reviewed,
    expansion_200_twenty_fourth_reviewed,
    expansion_200_twenty_ninth_reviewed,
    expansion_200_twenty_second_reviewed,
    expansion_200_twenty_seventh_reviewed,
    expansion_200_twenty_sixth_reviewed,
    expansion_200_twenty_third_reviewed,
)
from datacenter_atlas.verified_construction_core_v018 import (  # noqa: E402
    build_draft,
    validate_draft,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    batches = {
        "initial-three": expansion_200_initial_three,
        "initial-five": expansion_200_initial_five,
        "second-reviewed": expansion_200_second_reviewed,
        "third-reviewed": expansion_200_third_reviewed,
        "fourth-reviewed": expansion_200_fourth_reviewed,
        "fifth-reviewed": expansion_200_fifth_reviewed,
        "sixth-reviewed": expansion_200_sixth_reviewed,
        "seventh-reviewed": expansion_200_seventh_reviewed,
        "eighth-reviewed": expansion_200_eighth_reviewed,
        "ninth-reviewed": expansion_200_ninth_reviewed,
        "tenth-reviewed": expansion_200_tenth_reviewed,
        "eleventh-reviewed": expansion_200_eleventh_reviewed,
        "twelfth-reviewed": expansion_200_twelfth_reviewed,
        "thirteenth-reviewed": expansion_200_thirteenth_reviewed,
        "fourteenth-reviewed": expansion_200_fourteenth_reviewed,
        "fifteenth-reviewed": expansion_200_fifteenth_reviewed,
        "sixteenth-reviewed": expansion_200_sixteenth_reviewed,
        "seventeenth-reviewed": expansion_200_seventeenth_reviewed,
        "eighteenth-reviewed": expansion_200_eighteenth_reviewed,
        "nineteenth-reviewed": expansion_200_nineteenth_reviewed,
        "twentieth-reviewed": expansion_200_twentieth_reviewed,
        "twenty-first-reviewed": expansion_200_twenty_first_reviewed,
        "twenty-second-reviewed": expansion_200_twenty_second_reviewed,
        "twenty-third-reviewed": expansion_200_twenty_third_reviewed,
        "twenty-fourth-reviewed": expansion_200_twenty_fourth_reviewed,
        "twenty-fifth-reviewed": expansion_200_twenty_fifth_reviewed,
        "twenty-sixth-reviewed": expansion_200_twenty_sixth_reviewed,
        "twenty-seventh-reviewed": expansion_200_twenty_seventh_reviewed,
        "twenty-eighth-reviewed": expansion_200_twenty_eighth_reviewed,
        "twenty-ninth-reviewed": expansion_200_twenty_ninth_reviewed,
        "thirtieth-reviewed": expansion_200_thirtieth_reviewed,
        "thirty-first-reviewed": expansion_200_thirty_first_reviewed,
        "thirty-second-reviewed": expansion_200_thirty_second_reviewed,
        "thirty-third-reviewed": expansion_200_thirty_third_reviewed,
    }
    parser.add_argument("--batch", choices=sorted(batches), default="initial-three")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    batch = batches[args.batch]
    output = args.output_dir or batch.draft_path()
    if args.validate_only:
        manifest = validate_draft(output, batch.contract_path(), batch.REVIEW_PINS)
    else:
        manifest = build_draft(batch.contract_path(), batch.REVIEW_PINS, output)
    print(json.dumps({key: manifest[key] for key in (
        "release_status", "publishable_as_final", "counts"
    )}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
