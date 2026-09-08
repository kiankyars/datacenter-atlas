"""Reviewed initial-three v0.18 draft inputs; never refresh pins during a build.

The source-level review distinguishes CapitaLand's active Tower 2 from completed
Tower 1, the explicitly named ITPH campus point from a building footprint, and
LAX01's exact first-facility address from its wider property-development program.
These are opt-in draft additions, not completion of the 100-site expansion.
"""

from pathlib import Path

from .verified_construction_core_v018 import ROOT, ReviewPins


CONTRACT_RELATIVE_PATH = (
    "definitions/verified-construction-core-v0.18-initial-three-batch.json"
)
DRAFT_RELATIVE_PATH = (
    "verified_construction_core/2026-08-20-v0.18-draft-initial-three"
)
REVIEW_PINS = ReviewPins(
    contract_sha256="17d860b742f34ab0bad5eeeb42cea0bdbdf8015107cdcc031902a36580bf3ec0",
    source_sha256={
        "capitaland-mumbai-status": (
            "81bb8898883c4e97b2a4fbb699bdf09e71a31f9d4595dd7e402471478490d76f"
        ),
        "capitaland-mumbai-locator-identity": (
            "09898db5b9d5f5d0cb11997246386076ccbdbf9ad3bfbef3774ac5d24f13f666"
        ),
        "capitaland-mumbai-locator": (
            "b128d0ba3efcba2cae7d3ca1bb026295a435a753def07d1289ca54325bdb77fa"
        ),
        "capitaland-hyderabad-status": (
            "ba74bf245c5a57cc7246648c4b26a401285e79722fe98281e45845a85dc4225e"
        ),
        "capitaland-hyderabad-locator-identity": (
            "777973da0ac177393e6a74d05c42acf3cfc5168946d6fdbad015eb3253c774c2"
        ),
        "capitaland-hyderabad-locator": (
            "ac2a04eb0ff0c2d4aa0203e41edf074d69823d54e6ba1a9893846500e8b35e97"
        ),
        "goodman-lax01-status": (
            "4efe76bd4eb2380a278aa9111a344f34e12cfe5a80b32ab4e27d3823ed4820eb"
        ),
        "goodman-lax01-identity": (
            "9600c641b6d55c2fbac976f35606fee3d130ca7f3da225516fe200ee0b7ed177"
        ),
        "goodman-lax01-locator": (
            "45df7978232816236e7017c737d6218f205d2d1c3a3def624627dda1deca647f"
        ),
    },
    acceptance_sha256={
        "curated:capitaland-dc-navi-mumbai-campus:tower-2": (
            "a2733928c8cc5c1727680b378bff5f99183c15ea1b4189871c1ce91792d39f2a"
        ),
        "curated:capitaland-dc-itph-hyderabad:current-facility-build": (
            "1c83d4cc08f872317852bebf49b8ec7c92112a95558912e5c0b3533a408a5a11"
        ),
        "curated:goodman-lax01-los-angeles-program-anchor:first-site-current-development": (
            "02fb5172936911a10736f621eaeea0cb153c67944985ff2afd5c785d4cfc2d52"
        ),
    },
)


def contract_path(root: Path = ROOT) -> Path:
    return root / CONTRACT_RELATIVE_PATH


def draft_path(root: Path = ROOT) -> Path:
    return root / DRAFT_RELATIVE_PATH
