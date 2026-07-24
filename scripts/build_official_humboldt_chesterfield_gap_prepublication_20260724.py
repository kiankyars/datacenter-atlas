"""Build the private Humboldt and Chesterfield prepublication candidate."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datacenter_atlas.official_humboldt_chesterfield_gap_prepublication_20260724 import (
    main,
)

if __name__ == "__main__":
    raise SystemExit(main())
