#!/usr/bin/env python3
"""Generate a standalone atlas page with GeoJSON embedded in the document."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


TEMPLATE_PATH = Path(__file__).with_name("atlas-template.html")
DATA_PLACEHOLDER = "__ATLAS_DATA_JSON__"


def load_feature_collection(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError("input must be a GeoJSON FeatureCollection")
    features = data.get("features")
    if not isinstance(features, list):
        raise ValueError("FeatureCollection.features must be an array")
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"features[{index}] must be a GeoJSON Feature")
        if not isinstance(feature.get("properties"), dict):
            raise ValueError(f"features[{index}].properties must be an object")
    return data


def serialize_for_script(data: dict[str, Any]) -> str:
    """Serialize JSON without allowing data to terminate its script element."""
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_atlas(data: dict[str, Any], template: str) -> str:
    if template.count(DATA_PLACEHOLDER) != 1:
        raise ValueError("atlas template must contain exactly one data placeholder")
    return template.replace(DATA_PLACEHOLDER, serialize_for_script(data))


def generate(input_path: Path, output_path: Path) -> None:
    data = load_feature_collection(input_path)
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = render_atlas(data, template)
    output_path.write_text(rendered, encoding="utf-8")
    manifest_path = output_path.parent / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = manifest.get("files")
        if not isinstance(files, dict):
            raise ValueError("release manifest files must be an object")
        raw = rendered.encode("utf-8")
        files[output_path.name] = {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Embed an exported Data Center Atlas GeoJSON file in an interactive map."
    )
    parser.add_argument("input", type=Path, help="Atlas GeoJSON FeatureCollection")
    parser.add_argument("output", type=Path, help="Generated standalone HTML")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate(args.input, args.output)


if __name__ == "__main__":
    main()
