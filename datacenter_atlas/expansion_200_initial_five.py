"""Reviewed cumulative five-site draft; original three-site snapshot stays frozen."""

from pathlib import Path

from .expansion_200_initial_three import REVIEW_PINS as FIRST_THREE_PINS
from .verified_construction_core_v018 import ROOT, ReviewPins


CONTRACT_RELATIVE_PATH = (
    "definitions/verified-construction-core-v0.18-initial-five-batch.json"
)
DRAFT_RELATIVE_PATH = (
    "verified_construction_core/2026-08-20-v0.18-draft-initial-five"
)
REVIEW_PINS = ReviewPins(
    contract_sha256="c4aa4302d3bf467c95caaca1167b4da4a3edb9d5e3cb7977ad4f683c0004d69e",
    source_sha256={
        **FIRST_THREE_PINS.source_sha256,
        "microsoft-kirkkonummi-status": (
            "3962bde5fa765d26fca67490c32a7a6d7ea21e558b269540f4d4181ca27c259e"
        ),
        "microsoft-kirkkonummi-identity": (
            "a1384b8c776c1ad4315f60c6ccb1e48ecf74c9c9b9662a85364f3a6195f38341"
        ),
        "microsoft-kirkkonummi-locator": (
            "08d856e2bff0c9741653d44dcb362267b88b279040b7fce7f503bfc008584b9d"
        ),
        "microsoft-espoo-status": (
            "374feeb259e25fca9471e4f4ae45bc3606324c61c198fb2af6bf6a66402a2a88"
        ),
        "microsoft-espoo-identity": (
            "206f4f4260f3bdda7fd5422503d9e90adb331642e782c82859a47fe6158df142"
        ),
        "microsoft-espoo-locator": (
            "558329db924ca0649d25ac6fa945310e2a9c08972b546facb67477bcf67589a6"
        ),
    },
    acceptance_sha256={
        "curated:capitaland-dc-navi-mumbai-campus:tower-2": (
            "5a725a43f4706fd40bad19a4e73f30559d493ef607ee5b651abe05e889d210ea"
        ),
        "curated:capitaland-dc-itph-hyderabad:current-facility-build": (
            "fb3a94ff567f04ddf46bf874988192d4a8d552dfd6a27a7d1b7274135d56324d"
        ),
        "curated:goodman-lax01-los-angeles-program-anchor:first-site-current-development": (
            "f96cc8861e9a0e6339329926cd1c0c03b52bbfbf3fb0473177196143b55f2a8a"
        ),
        "curated:microsoft-finland-kirkkonummi-campus:building-1": (
            "fafd12cacc030a07424698e6e7e1ac1bd5238fef82006883b2c96c8595861348"
        ),
        "curated:microsoft-finland-espoo-hepokorpi-campus:second-building": (
            "ae926e8b5c40580a489284eb5141a47dd6df2d1482f60ab133ce0dd6742e5c34"
        ),
    },
)


def contract_path(root: Path = ROOT) -> Path:
    return root / CONTRACT_RELATIVE_PATH


def draft_path(root: Path = ROOT) -> Path:
    return root / DRAFT_RELATIVE_PATH
