"""Workspace import shim for the nested installable package.

This keeps ``python -m datacenter_atlas`` and repository-root unittest discovery working without an
editable install, while the inner package remains directly installable from this directory.
"""

from __future__ import annotations

import importlib
from pathlib import Path
import sys

from .datacenter_atlas import *  # noqa: F401,F403
from .datacenter_atlas import __all__ as __all__, __version__ as __version__


_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.append(_project_root)


for _module_path in sorted((Path(_project_root) / "datacenter_atlas").glob("*.py")):
    # The executable wrapper needs its own loader for `python -m` from the parent directory.
    if _module_path.stem.startswith("__") or _module_path.stem == "goodman_databank_lax01_official_enrichment_20260722":
        continue
    _module_name = _module_path.stem
    _module = importlib.import_module(f".datacenter_atlas.{_module_name}", __name__)
    sys.modules[f"{__name__}.{_module_name}"] = _module
    setattr(sys.modules[__name__], _module_name, _module)
