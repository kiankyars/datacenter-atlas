"""Reviewed cumulative expansion checkpoint; earlier snapshots stay frozen."""

from pathlib import Path

from .verified_construction_core_v018 import ROOT, ReviewPins


CONTRACT_RELATIVE_PATH = (
    "definitions/verified-construction-core-v0.18-second-reviewed-batch.json"
)
DRAFT_RELATIVE_PATH = (
    "verified_construction_core/2026-08-20-v0.18-draft-second-reviewed"
)
REVIEW_PINS = ReviewPins(
    contract_sha256="9395d1124fa81b950dfc55e7c6f9e6bf3837e881d6f02a017c6c6a042a5a5e50",
    source_sha256={
        "capitaland-mumbai-status": "81bb8898883c4e97b2a4fbb699bdf09e71a31f9d4595dd7e402471478490d76f",
        "capitaland-mumbai-locator-identity": "09898db5b9d5f5d0cb11997246386076ccbdbf9ad3bfbef3774ac5d24f13f666",
        "capitaland-mumbai-locator": "b128d0ba3efcba2cae7d3ca1bb026295a435a753def07d1289ca54325bdb77fa",
        "capitaland-hyderabad-status": "ba74bf245c5a57cc7246648c4b26a401285e79722fe98281e45845a85dc4225e",
        "capitaland-hyderabad-locator-identity": "777973da0ac177393e6a74d05c42acf3cfc5168946d6fdbad015eb3253c774c2",
        "capitaland-hyderabad-locator": "ac2a04eb0ff0c2d4aa0203e41edf074d69823d54e6ba1a9893846500e8b35e97",
        "goodman-lax01-status": "4efe76bd4eb2380a278aa9111a344f34e12cfe5a80b32ab4e27d3823ed4820eb",
        "goodman-lax01-identity": "9600c641b6d55c2fbac976f35606fee3d130ca7f3da225516fe200ee0b7ed177",
        "goodman-lax01-locator": "45df7978232816236e7017c737d6218f205d2d1c3a3def624627dda1deca647f",
        "microsoft-kirkkonummi-status": "3962bde5fa765d26fca67490c32a7a6d7ea21e558b269540f4d4181ca27c259e",
        "microsoft-kirkkonummi-identity": "a1384b8c776c1ad4315f60c6ccb1e48ecf74c9c9b9662a85364f3a6195f38341",
        "microsoft-kirkkonummi-locator": "08d856e2bff0c9741653d44dcb362267b88b279040b7fce7f503bfc008584b9d",
        "microsoft-espoo-status": "374feeb259e25fca9471e4f4ae45bc3606324c61c198fb2af6bf6a66402a2a88",
        "microsoft-espoo-identity": "206f4f4260f3bdda7fd5422503d9e90adb331642e782c82859a47fe6158df142",
        "microsoft-espoo-locator": "558329db924ca0649d25ac6fa945310e2a9c08972b546facb67477bcf67589a6",
        "goodman-par01-registry-identity": "a408d07a283082c583c27706ab1030ab6b0ea02b707ed28a44d406f16209aad7",
        "goodman-par01-project-identity": "693421e358a831cf118784dbef7b0b3322f0ae28c50696f3a6a53b014318a705",
        "goodman-par01-inquiry-identity": "983fee3118ea8478abc115b2b2070e7d59debb9f01b9397a587e1475dbfbadce",
        "goodman-par02-report-identity": "a9b4d443e99b8855c34bb79e1ad5212759804b8232195b24ac52bca7e1c9c484",
        "goodman-par02-inquiry-identity": "f2134f0029bb96e58023fa42d4aded80a8ef77c623ec80b3e12b6c27996439bd",
        "goodman-ams01-usgbc-identity": "d80185a1c5b255227fdc15824f72534a560c91aa5ea536fec002f433e791a89e",
        "goodman-ams01-permit-identity": "581d2f8d2c5b76318586fa19ada6d5e311bb32e3f141e0ac0c321e6c777ec0ae",
        "goodman-par01-ign-locator": "28dcd2b476a3dd81ea799633838882b2cb34a7e9844b03e773de28b762237afa",
        "goodman-par02-ign-locator": "2e48f2e939362d115cfcc5cc86b4829bef0a4ea68be099272df9e89b992ce693",
        "goodman-ams01-notice-locator": "bb098e6702fd13dcdc720b1d8f54c9ccd6d20c175951fe8bbbe6c3c2398d6152",
        "goodman-ams01-notice-crs": "4fdcdeac8e447f02294a06c8a02ded6cd2aa58e25823ef3581b56f69bd7bcf14",
        "goodman-par01-status": "b99ea7508a8974e34a6d6883ea3c2265c8a50c87e4dba327c9e8cbe85841feda",
        "goodman-par02-status": "975abb47bc166332b7a6f4be9f36225ea34d4277189203d661dedbfde3d06f92",
        "goodman-ams01-status": "d45c102caa1b55ad2ead40402b4c63102bdc7db8762997addadc9bb309f06add",
        "goodman-fra02-city-identity": "345bdbd2674c0b12964bf2c5753a9ae23c2908778c089f5700ad874ceb9550b2",
        "goodman-fra02-brochure": "8e379b69f1adeab59caae671eb2f0217264e05fbc917aeadcbd2a9dfa551051f",
        "goodman-fra02-map-locator": "762ba2a930db06891aaec918234c25a0781361ea9c7c308ee34f11ce4f985936",
        "goodman-fra02-status": "f03c4dc90255f99630e80a4ad799761a9dc4c7c9e03b89f44a243fd686731df5",
        "us-amazon-identity": "a414f9aaaa79e941ee8cbffb55d72dda2cf6440bc2d7d9ff019fecfe51790723",
        "us-amazon-plan": "2a5444144c0437303f74034a8f1ea58706f6c7bfa828f9806f64f2b674f05a89",
        "us-amazon-locator": "219117c9e8414a64a5dbdb96c435f06dd7b0b30a4c193532e0ef0d67ebf07d99",
        "us-dulles-identity": "7c00a34d556171fae80f82af6ab21ab4bf923ebd7d3ab5d9d0c7c5fe973f9fe2",
        "us-dulles-locator": "616c639acf1c90ee283a1cb299bd81df89a7cecb8b1528e21ded215d808207e2",
        "us-helios-identity": "de2e09a97d084f019d130ce8afacb0ba7dbede2f0bdf309e1ca735bf8845aa86",
        "us-helios-phase2-identity": "91facfef4f55270bc119e6f2be583465a2e0a2437c339ef90cc8c827971aba03",
        "us-helios-locator": "3f2fe51754068f6782a95b7dc0d3ad3c21f1ba3365401dd50a2175be8227bcca",
        "us-amazon-county-portal-provenance": "535a82f49afa6a170aa6f07c6cd702c27fd0e90702f018119dda8d98242dd7f4",
        "us-amazon-status": "3bd99281b9d2ccc9698db532b9487dd37d080d13b56a3edd4b37c2a4ecdf8d63",
        "us-dulles-status": "0b7cda2b8a1800afcef8d34aeeb907f96a50a49674910b07e3cfe1e6b6da3ee5",
        "us-helios-status": "da687ad7b0adc80e9e015ba4c13cccc13385d8b3fdf4d086f2dfab45232e543c",
    },
    acceptance_sha256={
        "curated:capitaland-dc-navi-mumbai-campus:tower-2": "8c7c7042a3ff677165a535a9ad2a4b87bf0ff8f1f1382d92f6013a4830f76b0a",
        "curated:capitaland-dc-itph-hyderabad:current-facility-build": "7b494b6d3ca7c38ec0fd376c5470f21dfd6e342e7b9ad918ef1696b5dbaa4194",
        "curated:goodman-lax01-los-angeles-program-anchor:first-site-current-development": "09337b64015d6b1e3b15220df18a89b0d764756637d9b6287b575564b47717dd",
        "curated:microsoft-finland-kirkkonummi-campus:building-1": "e3e4d19683cf84e317c28279f0b88ca3ee68c03fc06b05665271c03362e63fb1",
        "curated:microsoft-finland-espoo-hepokorpi-campus:second-building": "f953c72317247d1e352297366d23265c550384aa9eead512591b13160f32457a",
        "curated:goodman-par01-paris-data-centre-campus:phase-1-current-development": "ef7b7092701f4910d45a2c6988e92de05bbf4b06f95f09145f0d111ada4c4ae3",
        "curated:goodman-par02-paris-data-centre-campus:phase-1-current-development": "e36e763c9879e6579e116b722e5ac9772dfe4330aba42eb95b018709b8a45810",
        "curated:goodman-ams01-amsterdam-data-centre-campus:phase-1-current-development": "411cf50ff187f23d05f01d1a6fbfc668d42da5f5515bdbf8e0a1c1be4cead78c",
        "curated:goodman-fra02-frankfurt-data-centre-campus:phase-1-current-development": "1dabb4bd6c5bf932809916afa052f14a4a491df16aaaf6200615fda4de0e2c74",
        "curated:amazon-falls-township-innovation-campus:active-buildout": "7f00d19fb40f3ef78c2a0e66fb95135a67b0b79f1853bf65051ef5f85b010bb8",
        "curated:digital-realty-digital-dulles-campus:current-96mw-development": "e23d621712c7429634498f23ed0d576eca357a9fd49dceecc4d1c7b0ae0caba7",
        "curated:galaxy-helios-data-center-campus:phase-2-260mw-critical-it-build": "542c74eb2876699094155e850aa55396336fd3d7b225817a47da6e6665b590e5",
    },
)


def contract_path(root: Path = ROOT) -> Path:
    return root / CONTRACT_RELATIVE_PATH


def draft_path(root: Path = ROOT) -> Path:
    return root / DRAFT_RELATIVE_PATH
