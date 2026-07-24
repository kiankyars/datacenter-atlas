"""Fail-closed current-coverage ledger v24 successor.

V24 replaces eight accepted v23 contracts with the seed-v83 public chain and
its current satellite queue. The bounded seed-v71 catalog and analyst review
remain explicitly historical review contracts; they are not seed-v83 imagery
coverage. Intermediate seeds, queues, source-assessment wrappers, raw machine
change runs, and technical incidents remain non-additive lineage rather than
standalone schema-v4 coverage contracts.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
from typing import Any, Callable, Iterator, Mapping, Sequence

from . import current_coverage_v22 as _v22
from . import current_coverage_v23 as _v23


V24_LEDGER_ID = "current-coverage-2026-07-21-v24"
V24_GENERATED_AT: str | None = "2026-07-21T19:02:00Z"
V24_DEFINITION_PATH = "sources/current-coverage-2026-07-21-v24.json"
V24_BUNDLE_PATH = "current_coverage_ledgers/2026-07-21-v24"
V24_DEFINITION_SHA256: str | None = (
    "50dd329704c38e127a206b2c3fda4c45deebe2592406e21edc365f4022d5fb5a"
)
REPLACEMENT_8_SHA256: str | None = (
    "ea0c3a7a279f6f7b619ac9856a1c65df38eaa9b5d6e74c5cf004539a0e1f179d"
)
HISTORICAL_2_SHA256: str | None = (
    "e3d3fca984a113f9f94fad8146889c8a39a2adc05a5a0f8f05d20d10e27a3a36"
)
ADDED_ARTIFACTS_SHA256: str | None = (
    "6bc7a9d47b4612864699918b1214473f9cf441e56ae0cfe938c9e039c5c41c48"
)
ALL_ENTRIES_SHA256: str | None = (
    "f1b9747f1d1304b0ff3e5c7c7cde76eb7caa1112eb729a9df0dfdb7553fab226"
)

DEFINITION_SCHEMA_VERSION_V4 = _v23.DEFINITION_SCHEMA_VERSION_V4
LEDGER_SCHEMA_VERSION_V4 = _v23.LEDGER_SCHEMA_VERSION_V4
LEDGER_FORMAT_V4 = _v23.LEDGER_FORMAT_V4
BUNDLE_FORMAT_V4 = _v23.BUNDLE_FORMAT_V4
ARTIFACT_KINDS_V4 = _v23.ARTIFACT_KINDS_V4
RECORD_UNITS_V4 = _v23.RECORD_UNITS_V4
SCOPE_POLICY = _v23.SCOPE_POLICY
BUNDLE_FILES = _v23.BUNDLE_FILES
LEDGER_FILENAME = _v23.LEDGER_FILENAME
MANIFEST_FILENAME = _v23.MANIFEST_FILENAME
MANIFEST_HASH_FILENAME = _v23.MANIFEST_HASH_FILENAME

V23_BASE_LINEAGE = {
    "definition": {
        "bytes": 164_074,
        "path": "sources/current-coverage-2026-07-21-v23.json",
        "sha256": "eca133b3f22e2ae58a3e90e42644cc1dad9d3849e2014a858529c270ccdf5687",
    },
    "ledger": {
        "bytes": 109_832,
        "path": (
            "current_coverage_ledgers/2026-07-21-v23/"
            "current-coverage-ledger.json"
        ),
        "sha256": "37d7a98e5dfdb310991ec0bafe88007dee6fd01fab01dc9d19c57d49a7296378",
    },
    "ledger_id": "current-coverage-2026-07-21-v23",
    "manifest": {
        "bytes": 30_042,
        "path": "current_coverage_ledgers/2026-07-21-v23/manifest.json",
        "sha256": "a59aae0d71d9e66eefd65b0fe3c84412481483869c54114345f34964c8fe68bc",
    },
}
V23_SIDECAR = {
    "bytes": 80,
    "path": "current_coverage_ledgers/2026-07-21-v23/manifest.sha256",
    "sha256": "ed4015331863bc362a3f37e040ac3eb58bc47219cd07690d7f9e9b36e7a7bf31",
}
V23_BUNDLE_TREE_SHA256 = (
    "4b8c409e928a7494afce90d7e1e7388d446bb6ff96a0003216ecc3c332799300"
)

ARTIFACT_REPLACEMENTS = {
    "construction-map-public-open-v29": "construction-map-public-open-v30",
    "construction-master-public-open-v29": "construction-master-public-open-v30",
    "construction-timeline-public-open-v6": "construction-timeline-public-open-v7",
    "coverage-audit-public-open-v29": "coverage-audit-public-open-v30",
    "exact-identity-decisions-public-open-v9": (
        "exact-identity-decisions-public-open-v10"
    ),
    "federation-public-open-v33": "federation-public-open-v34",
    "satellite-queue-open-seed-v71": "satellite-queue-open-seed-v83",
    "seed-epoch-official-v73": "seed-epoch-official-v83",
}
HISTORICAL_ARTIFACT_IDS = frozenset(
    {
        "satellite-catalog-open-seed-v71-active-explicit-final-v1",
        "satellite-change-review-open-seed-v71-active-explicit-11-review-v1",
    }
)
ADDED_ARTIFACT_IDS: frozenset[str] = frozenset(
    {
        "satellite-catalog-open-seed-v83-active-explicit-"
        "new-projects-final-v1",
        "satellite-change-review-open-seed-v83-active-explicit-"
        "new-projects-3-review-v2",
    }
)
REMOVED_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS)
REPLACEMENT_ARTIFACT_IDS = frozenset(ARTIFACT_REPLACEMENTS.values())
NEW_ARTIFACT_IDS = REPLACEMENT_ARTIFACT_IDS | ADDED_ARTIFACT_IDS
UNCHANGED_40_SHA256: str | None = (
    "6178822f9c84a39cabef04a370b852b70db3bc25906202f4734ed0dbe14a19d1"
)
REMOVED_8_SHA256: str | None = (
    "c2a0baf445ce80a24bb1a3016ebc02c107f28aafce2a02d6f8e93027c0dee2ed"
)
PARITY_GAPS_SHA256: str | None = (
    "4d2b0f8eb00b6fa01dbbf981e9554e495595a03b34c7c6b44eb968f3ad2ca3ec"
)

PENDING_DOWNSTREAM_REPLACEMENTS: dict[str, Mapping[str, Any] | None] = {}
PENDING_DOWNSTREAM_PIN_BLUEPRINT: dict[str, Mapping[str, Any]] = {}

# These accepted artifacts are provenance or incident inventory, not standalone
# schema-v4 coverage contracts. Their facts are either subsumed by v83 or have
# no honest artifact-kind/record-unit representation in the controlled
# vocabulary. Keeping the decision explicit prevents accidental additive reuse.
NON_LEDGER_ARTIFACT_DECISIONS: Mapping[str, Mapping[str, Any]] = {
    "site-coordinate-assessment-2026-07-21-v4": {
        "manifest": {
            "bytes": 1_792,
            "path": (
                "source_artifacts/site-coordinate-assessment-2026-07-21-v4/"
                "manifest.json"
            ),
            "sha256": (
                "8bcd9842af00890e4820e2b011a9fa799a1c4d5c98b0a77c4dc874c79b4c04b8"
            ),
        },
        "reason": "subsumed_nonadditive_seed_provenance",
    },
    "global-official-builds-six-candidate-2026-07-21-v1": {
        "manifest": {
            "bytes": 1_727,
            "path": (
                "source_artifacts/"
                "global-official-builds-six-candidate-2026-07-21-v1/"
                "manifest.json"
            ),
            "sha256": (
                "20b0788dba18402cf1b6bb8874ec6cd66f86000ff85f620c7e0167bf7e1894cd"
            ),
        },
        "reason": "subsumed_nonadditive_seed_provenance",
    },
    "federation-v32-partial-publication-incident-2026-07-21-v1": {
        "manifest": {
            "bytes": 1_122,
            "path": (
                "source_artifacts/"
                "federation-v32-partial-publication-incident-2026-07-21-v1/"
                "manifest.json"
            ),
            "sha256": (
                "4ef894097a41683a6d446e2c93e0a58127ceb1f4b7bf7b18e6cfce8eb9f51891"
            ),
        },
        "reason": "technical_incident_has_no_schema_v4_contract_kind",
    },
    "satellite-change-explicit-v1-disposition": {
        "manifest": {
            "bytes": 610,
            "path": (
                "satellite_change_run_dispositions/"
                "2026-07-21-open-seed-v71-active-explicit-001-v1/"
                "manifest.json"
            ),
            "sha256": (
                "81117523744d802d50ad08d65d4192c1673b0508b421a44b3e969b6e268a00cc"
            ),
        },
        "reason": "unreviewed_machine_change_has_no_schema_v4_contract_kind",
    },
    "satellite-change-open-seed-v83-active-explicit-new-projects-final-v1": {
        "manifest": {
            "bytes": 25_320,
            "path": (
                "satellite_change_runs/"
                "2026-07-21-open-seed-v83-active-explicit-"
                "new-projects-final-v1/batch-manifest.json"
            ),
            "sha256": (
                "aece77761174823eb4c2a2a58ea5aa85e191dbef28b490ed1de7b57cb12a4828"
            ),
        },
        "reason": "unreviewed_machine_change_has_no_schema_v4_contract_kind",
        "tree": {
            "path": (
                "satellite_change_runs/"
                "2026-07-21-open-seed-v83-active-explicit-"
                "new-projects-final-v1"
            ),
            "sha256": (
                "42b4f1cec01050bb56bf375e74e7c4430e70587bcd94814ee8ccbff43881146a"
            ),
        },
    },
    "satellite-change-v83-post-run-order-assertion-incident-v1": {
        "manifest": {
            "bytes": 2_414,
            "path": (
                "satellite_change_run_incidents/"
                "2026-07-21-open-seed-v83-post-run-order-assertion-v1/"
                "incident.json"
            ),
            "sha256": (
                "2a1df815a1c3c7ea1d7a2762ed1ec34266e06312219a8e40a8d7239506c7a5a7"
            ),
        },
        "reason": "technical_incident_has_no_schema_v4_contract_kind",
        "tree": {
            "path": (
                "satellite_change_run_incidents/"
                "2026-07-21-open-seed-v83-post-run-order-assertion-v1"
            ),
            "sha256": (
                "b5605169b5668a339989fa518cae18f61e54e79a70be58470c521da921217ee4"
            ),
        },
    },
    "satellite-review-v83-premature-publication-control-incident-v1": {
        "manifest": {
            "bytes": 1_361,
            "path": (
                "satellite_change_reviews/"
                "2026-07-21-open-seed-v83-active-explicit-"
                "new-projects-3-review-v2/publication-incident.json"
            ),
            "sha256": (
                "a69b9167ebb5268e518f7b4d64652e973450bd5c3396e9e9df974483322a738b"
            ),
        },
        "reason": "technical_incident_has_no_schema_v4_contract_kind",
    },
    **{
        artifact_id: {
            "manifest": {
                "bytes": byte_count,
                "path": f"source_artifacts/{artifact_id}/manifest.json",
                "sha256": sha256,
            },
            "reason": "subsumed_nonadditive_seed_provenance",
        }
        for artifact_id, byte_count, sha256 in (
            (
                "site-coordinate-assessment-2026-07-21-v5",
                2_022,
                "b05492a0454502e332c6517b60e48a99f3897f29dfae9ccd4d69569da3173b34",
            ),
            (
                "global-official-builds-next-tranche-2026-07-21-v1",
                1_791,
                "5cdf7bba0090ee2a67af2699257a6557ee1be16dcafb9d8560993127b714cce7",
            ),
            (
                "global-official-builds-regional-gap-2026-07-21-v1",
                1_795,
                "43d71b155b816b5b708cda78fff80b6646b83d4b5dc50b146a648400899b220f",
            ),
            (
                "global-official-builds-china-gap-2026-07-21-v1",
                1_781,
                "6de9a1a2e0b05a1b4523d45cc10a9cba8ecb36c3893243bb789f9687c26c6db8",
            ),
            (
                "global-official-builds-asia-gap-2026-07-21-v1",
                1_663,
                "ad12e66986122bd4d0076be6d94e116a7c38d2d4d78ef5300ea357d4851ac37b",
            ),
            (
                "global-official-builds-latam-caribbean-gap-2026-07-21-v1",
                1_706,
                "732590c83c47ce86b7eeed1c738ab2f9fc12b79b05c0043566d646a08c0ab3bb",
            ),
            (
                "global-official-builds-africa-gap-2026-07-21-v1",
                1_817,
                "c859d9a429729710d92f43fadf2570551a9959485c5c3ace005b612376b1478a",
            ),
            (
                "global-official-builds-middle-east-turkiye-gap-2026-07-21-v1",
                1_719,
                "11884537841f95d92042ac6438f837034ec51b3c249a1bb6929cd622d089cca2",
            ),
            (
                "global-official-builds-cee-gap-2026-07-21-v1",
                1_744,
                "13ffdc16826e4fc1caf75b3b9c97fe8f2176193247512992254bd8ae114bc4f9",
            ),
            (
                "global-official-builds-oceania-gap-2026-07-21-v1",
                1_708,
                "4c60b65554242278784ff726c6e176cb2ed70d9a2d1d1c062a3d729d87d77c85",
            ),
        )
    },
    **{
        f"seed-epoch-official-v{version}": {
            "manifest": {
                "bytes": byte_count,
                "path": (
                    f"releases/2026-07-21-open-seed-v{version}/manifest.json"
                ),
                "sha256": sha256,
            },
            "reason": "superseded_nonadditive_seed_lineage",
        }
        for version, byte_count, sha256 in (
            (74, 12_950, "7167225f3d530ea404a8334d63c18e037364e38d22cfef49773129e81cbeba56"),
            (75, 13_106, "7f121051b6af6c82a1c48011e7c471153b5047dd428addd7662dccb0c3a232de"),
            (76, 13_348, "6d176800502f59f268d6ef1040e6701dc1d14e4f21f2d3ecbe8ec86cb4cf917b"),
            (77, 13_615, "a35f3c064aabda5598d336cda264e4b798a516afe96331074f51d33fada4b7bb"),
            (78, 13_773, "4f9e1323f8db9d440c0fe692b7d453fbcca4b02a5296eb7f4c7796e850a0e04f"),
            (79, 13_885, "4eaceee00a0ed0e9073bc6cd19a8f82c97a442f05e773615ee1bb470a95a5c71"),
            (80, 14_003, "a9a89bb89aa0febd32a90b7fb30134f499ad360e08e28eb358bcfd9fe74934d1"),
            (81, 14_362, "015c1758d9d6a44faf921fc4402dd5653c02dd96bb6a46ab3164aa83d183938d"),
            (82, 14_564, "2a0ddb8a9ded0e8ce9d01a56cfbfd16d9550decabdb141e96f849f404c2de295"),
        )
    },
    "satellite-queue-open-seed-v73": {
        "manifest": {
            "bytes": 17_330,
            "path": (
                "satellite_review_queues/2026-07-21-open-seed-v73/"
                "manifest.json"
            ),
            "sha256": (
                "bf6a6e94ad3cad3f3f0d67b54ca4821c0fa4db7a2c50711ef6500c1d4aba2af4"
            ),
        },
        "reason": "superseded_noncurrent_queue_lineage",
    },
    "global-official-builds-canada-mexico-caribbean-gap-2026-07-21-v1": {
        "manifest": {
            "bytes": 1_809,
            "path": (
                "source_artifacts/"
                "global-official-builds-canada-mexico-caribbean-gap-"
                "2026-07-21-v1/manifest.json"
            ),
            "sha256": (
                "0a38f1fd7f269c568a7db1f05416766ef56e5285a0000cd7b4219fb12361584a"
            ),
        },
        "reason": "pending_seed_integration",
        "tree": {
            "path": (
                "source_artifacts/"
                "global-official-builds-canada-mexico-caribbean-gap-"
                "2026-07-21-v1"
            ),
            "sha256": (
                "4b6a15ba20ce8a5134952f4dcdfbaa7096600dcfbce6d5397d3b0007126fad3b"
            ),
        },
    },
}

_ACCEPTED_FILES = {
    "construction map v30 coverage": (
        "construction_maps/2026-07-21-public-open-v30/coverage.json",
        7_524,
        "bb4eeb2cfafdc50e0b1fedf21feee4fdef399b7ddc460306b7cb0f128b48b61f",
        0o444,
    ),
    "construction map v30 definition": (
        "sources/construction-map-2026-07-21-public-open-v30.json",
        2_442,
        "47f2322edd2983bc8ed881edf8e0071d806df304cf773be2e215bcc1806d0847",
        0o444,
    ),
    "construction map v30 index": (
        "construction_maps/2026-07-21-public-open-v30/construction-map-index.json.gz",
        6_682_084,
        "dc5fcccf70fbd7232062134831bfdd68172013ae5d53a35ee5de8ac1fffaa718",
        0o444,
    ),
    "construction map v30 manifest": (
        "construction_maps/2026-07-21-public-open-v30/manifest.json",
        2_192,
        "73108a00068912f83233114fc2ab7ae79087e610d54226762512fe3cc8ef4360",
        0o444,
    ),
    "construction master v30 coverage": (
        "construction_master/2026-07-21-public-open-v30/coverage.json",
        8_550,
        "db046e49a5590fdbae810343d9efa9d4f34401a2c2bfdb513d8c552d8507a5aa",
        0o444,
    ),
    "construction master v30 definition": (
        "sources/construction-master-2026-07-21-public-open-v30.json",
        5_659,
        "981bfd4dcf9bcb6f00f6825c4ac74d62b2bfefeb019fbfa945b774c136683a63",
        0o444,
    ),
    "construction master v30 manifest": (
        "construction_master/2026-07-21-public-open-v30/manifest.json",
        9_720,
        "8f81ded9c9f351caa0f7a75afce8b4a7abe673c3a078c5bf5fd7bb1f75eabf1f",
        0o444,
    ),
    "coverage v30 definition": (
        "sources/coverage-audit-2026-07-21-public-open-v30.json",
        5_920,
        "8d23100aaf465a5464f3945cb4d55d4fe2b370f3ce5a8ebc6e493acdcd141eba",
        0o444,
    ),
    "coverage v30 manifest": (
        "audits/2026-07-21-public-open-coverage-v30/manifest.json",
        3_379,
        "5bd7257085f52258c5187f38f811148e8edb9a38d212fc44104f9368bf769b78",
        0o444,
    ),
    "federation v34 definition": (
        "sources/federation-2026-07-21-public-open-v34.json",
        1_788,
        "f01622e680fac69a3fc1ad78151d56cf5cd5b412a28efea91e998fceba367a82",
        0o444,
    ),
    "federation v34 index": (
        "federated_indexes/2026-07-21-public-open-v34/federated-index.json",
        35_181,
        "6389e18f6a1085e0a2cba577e412406187ea89d017e921aba6e7fb3edede60ba",
        0o444,
    ),
    "federation v34 manifest": (
        "federated_indexes/2026-07-21-public-open-v34/manifest.json",
        986,
        "31f2d60f266045f01af510f9fc16e541642231697167f3feaf3a70012a376503",
        0o444,
    ),
    "identity v10 accounting": (
        "exact_identity_decisions/2026-07-21-public-open-v10/accounting.json",
        981,
        "fc9c2b08983b785b3f5792068dd9b80262f2fa1bbf6dd1496dd7a6cb73b45794",
        0o444,
    ),
    "identity v10 definition": (
        "sources/exact-identity-decisions-2026-07-21-public-open-v10.json",
        1_736,
        "b68c6cd6f84405844b518dcf1aa421f86202c7d2f86c1325905333e5f281d78b",
        0o444,
    ),
    "identity v10 manifest": (
        "exact_identity_decisions/2026-07-21-public-open-v10/manifest.json",
        11_441,
        "5806448df1316aa56e4ba82a63961f5dd0b6337ee455de29929c369288a940fe",
        0o444,
    ),
    "seed v83 definition": (
        "sources/open-seed-2026-07-21-v83.json",
        98_808,
        "84534350a3cf40c7f85479b9d4d42b53604f1858d5325b79dfb0c93de03be4e7",
        0o444,
    ),
    "seed v83 manifest": (
        "releases/2026-07-21-open-seed-v83/manifest.json",
        14_812,
        "56f33ade743f50e36bd4b2d6f32fa71eaa2b117af79c8580f92d7319c77bd7d5",
        0o444,
    ),
    "timeline v7 coverage": (
        "construction_timelines/2026-07-21-public-open-v7/coverage.json",
        68_483,
        "45246273b5a84287a4da3633fa9dbb437f97976be23731f5998fd0f763c12c60",
        0o444,
    ),
    "timeline v7 definition": (
        "sources/construction-timeline-2026-07-21-public-open-v7.json",
        2_941,
        "2fa593cbb2f135e1e6feb5baf3e18efa0fd4b9a88a4b264884306a50e43aece1",
        0o444,
    ),
    "timeline v7 manifest": (
        "construction_timelines/2026-07-21-public-open-v7/manifest.json",
        3_897,
        "a5378eb55f42132193d1e82b97dec5a252e950fa5c4d0c22b278c404ad921265",
        0o444,
    ),
    "satellite queue v83 manifest": (
        "satellite_review_queues/2026-07-21-open-seed-v83/manifest.json",
        19_851,
        "cd31436eb4bc862096952403d70be33ed41d0e752a3a617ce2d175569049c9bd",
        0o444,
    ),
    "satellite queue v83 rows": (
        "satellite_review_queues/2026-07-21-open-seed-v83/satellite-review-queue.jsonl",
        553_692,
        "8792ee2d80ed9b44d3ef67d3511b29ca0f9160b8ebd641e7f54cf4f5db4e4251",
        0o444,
    ),
    "satellite catalog v83 manifest": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-final-v1/"
        "batch-manifest.json",
        65_077,
        "d8c99c8cd5f82f8474c4f7f0ab0ef5b002555583d083b6664ed5ae600b477a48",
        0o444,
    ),
    "satellite catalog v83 receipt": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-final-v1/"
        "selection-receipt.json",
        7_194,
        "ea98a8ceb3d3b457e84e1ae0db06ed28c12e39437c649c50f8c495dc3041fc45",
        0o444,
    ),
    "satellite catalog v83 receipt sidecar": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-final-v1/"
        "selection-receipt.sha256",
        89,
        "4009e5e33a6228fced49da22bab1c88723725f0caf46b3f00bf74ffcad583ba8",
        0o444,
    ),
    "satellite change review v83 analyst rows": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-3-review-v2/"
        "analyst-reviews.jsonl",
        6_447,
        "000751541195ca2bef05d4faddc323d6d886794eb91e294f23a0ed838dfda7d4",
        0o444,
    ),
    "satellite change review v83 blind decisions": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-3-review-v2/"
        "blind-decisions.json",
        4_646,
        "99dfa722aa3d6bd914d450dda528ccec5e7670eeb66157a85880d1356eb3c06a",
        0o444,
    ),
    "satellite change review v83 definition": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-3-review-v2/"
        "definition.json",
        6_622,
        "9328509714323a523b4adb8dd3a1131ae960c120f56a6beaf9ffb64d35f288c3",
        0o444,
    ),
    "satellite change review v83 manifest": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-3-review-v2/"
        "manifest.json",
        6_526,
        "4cbe507b44e830a92879079cc9f33290d9d64459e1b1a33a9d2944737e3eba33",
        0o444,
    ),
    "satellite change review v83 manifest sidecar": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-3-review-v2/"
        "manifest.sha256",
        80,
        "660acd37fd03906e36cf6a4e3cd6b86720fe463ef0aa44a73998b894e5b6ac3c",
        0o444,
    ),
    "satellite change review v83 publication incident": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-3-review-v2/"
        "publication-incident.json",
        1_361,
        "a69b9167ebb5268e518f7b4d64652e973450bd5c3396e9e9df974483322a738b",
        0o444,
    ),
    "satellite change review v83 summary": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-3-review-v2/"
        "summary.json",
        5_477,
        "7ff6f4ff7499892cfc9c38278b85a868fb264f5c6379277205d11a4ca0fd47e3",
        0o444,
    ),
    "historical satellite queue v71 manifest": (
        "satellite_review_queues/2026-07-21-open-seed-v71/manifest.json",
        17_073,
        "e62b514acc196c4a1318907b3509676542798ac5da89fda304f5485e0cfd1000",
        0o444,
    ),
    "satellite catalog v71 finalized manifest": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v71-active-explicit-final-v1/"
        "batch-manifest.json",
        64_864,
        "c930e7a0431540ead5fe54d8cc60808bc0e1e8a57ddea99acb01eacb94d25da9",
        0o444,
    ),
    "satellite catalog v71 finalized receipt": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v71-active-explicit-final-v1/"
        "selection-receipt.json",
        9_921,
        "cab75bcfb893002baa65a04bd3e2b1a104a510cf820076f7fcddecb5a2c665d2",
        0o444,
    ),
    "satellite change review v71 analyst rows": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
        "analyst-reviews.jsonl",
        24_913,
        "951321125a123cb3be788dfb4d5b44bfddd309318bd740b45671d06c62ab2059",
        0o444,
    ),
    "satellite change review v71 blind decisions": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
        "blind-decisions.json",
        6_890,
        "6e6bc074400b13d47c23953c2224ab50e12b4b6f2b48a1377237275b3edde0eb",
        0o444,
    ),
    "satellite change review v71 definition": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
        "definition.json",
        4_158,
        "b2e6acbd705f4d0229222bfa0e6d17532e3866225315280c578933e00bbd3ff2",
        0o444,
    ),
    "satellite change review v71 manifest": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
        "manifest.json",
        4_203,
        "d5184c13eca93b9f07711781665deca71d271ec263627437285e813cdb495b12",
        0o444,
    ),
    "satellite change review v71 summary": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
        "summary.json",
        3_352,
        "ccdc4ae77e550073469c8b1672d961e7be8a7e26ca4c1d782926effd3e6afeef",
        0o444,
    ),
}

_ACCEPTED_TREES = {
    "construction map v30": (
        "construction_maps/2026-07-21-public-open-v30",
        "67bc3870ddc2c34308ab0de5defe19ece9d9cea85f6f1ac5c1d4082b18714149",
    ),
    "construction master v30": (
        "construction_master/2026-07-21-public-open-v30",
        "32d3370e3604434886d305c2a0b129458bfbe1c4e823760f0ccc3a16a3519e30",
    ),
    "coverage v30": (
        "audits/2026-07-21-public-open-coverage-v30",
        "ca7212059190432d407908008e06a684380b04fe46bef75d4201bd7c045b0ed4",
    ),
    "federation v34": (
        "federated_indexes/2026-07-21-public-open-v34",
        "a65ae68300e8a6a5a4446e7b264485fcc850d96900de047c960370e57df46bf2",
    ),
    "identity v10": (
        "exact_identity_decisions/2026-07-21-public-open-v10",
        "22363d1472487077386510c51ee373b15b2c1ee9f6343d80267f98ca4cd4a5fa",
    ),
    "seed v83": (
        "releases/2026-07-21-open-seed-v83",
        "1cc39e4079c989d558c33ef63c3109919da533c5feabe9eb02c7cd8347e1d94d",
    ),
    "timeline v7": (
        "construction_timelines/2026-07-21-public-open-v7",
        "b7dd059de068366d12da84970ca750fc3a2872f59069b5563ac47c5e05ce568c",
    ),
    "satellite queue v83": (
        "satellite_review_queues/2026-07-21-open-seed-v83",
        "2b9fc5a30525e2e815154d1635c49badf06c436e354ccb04a4898e6f42d22eee",
    ),
    "satellite catalog v83": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-final-v1",
        "8f4409c43f34512c2b092c657fedc362bda1a1afbe0a0b23da53ef955edfe937",
    ),
    "satellite change review v83": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-3-review-v2",
        "b58368608ad2e37024ee3263c1ab6e7ff42d33272d392c9527ac97a8a53a1749",
    ),
    "satellite catalog v71 finalized": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v71-active-explicit-final-v1",
        "f2abbd23a18ac4ded2e4afa9acbdfa30240fc3b0015d89a01cdb4805ce308a6a",
    ),
    "satellite change review v71": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1",
        "2f671c8dee331e10f2b297145d6c7eb9efdf300f56592d32048ab075d7f9f2ad",
    ),
}

_SOURCE_TIMESTAMPS = {
    "construction map v30": (
        "construction_maps/2026-07-21-public-open-v30/manifest.json",
        "generated_at",
        "2026-07-21T18:11:00Z",
    ),
    "construction master v30": (
        "construction_master/2026-07-21-public-open-v30/manifest.json",
        "generated_at",
        "2026-07-21T18:04:00Z",
    ),
    "coverage v30": (
        "audits/2026-07-21-public-open-coverage-v30/manifest.json",
        "generated_at",
        "2026-07-21T18:20:30Z",
    ),
    "federation v34": (
        "federated_indexes/2026-07-21-public-open-v34/manifest.json",
        "generated_at",
        "2026-07-21T17:47:00Z",
    ),
    "identity v10": (
        "exact_identity_decisions/2026-07-21-public-open-v10/manifest.json",
        "recorded_at",
        "2026-07-21T17:50:27Z",
    ),
    "seed v83": (
        "releases/2026-07-21-open-seed-v83/manifest.json",
        "recorded_at",
        "2026-07-21T17:38:10Z",
    ),
    "timeline v7": (
        "construction_timelines/2026-07-21-public-open-v7/manifest.json",
        "generated_at",
        "2026-07-21T17:50:50Z",
    ),
    "satellite queue v83": (
        "satellite_review_queues/2026-07-21-open-seed-v83/manifest.json",
        "generated_at",
        "2026-07-21T18:05:10Z",
    ),
    "satellite catalog v83": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-final-v1/"
        "batch-manifest.json",
        "updated_at",
        "2026-07-21T18:18:47Z",
    ),
    "satellite change review v83": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-3-review-v2/"
        "manifest.json",
        "generated_at",
        "2026-07-21T18:52:30.000000Z",
    ),
    "satellite catalog v71 finalized": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v71-active-explicit-final-v1/"
        "batch-manifest.json",
        "updated_at",
        "2026-07-21T13:42:28Z",
    ),
    "satellite change review v71": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
        "manifest.json",
        "generated_at",
        "2026-07-21T14:24:30.000000Z",
    ),
}

_ACCEPTED_ROOT_NOT_BEFORE = {
    "satellite catalog v83": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-final-v1",
        "2026-07-21T18:20:13Z",
    ),
    "satellite change review v83": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v83-active-explicit-new-projects-3-review-v2",
        "2026-07-21T18:52:30Z",
    ),
    "satellite catalog v71 finalized": (
        "satellite_review_runs/"
        "2026-07-21-open-seed-v71-active-explicit-final-v1",
        "2026-07-21T14:05:15Z",
    ),
    "satellite change review v71": (
        "satellite_change_reviews/"
        "2026-07-21-open-seed-v71-active-explicit-11-review-v1",
        "2026-07-21T14:24:30Z",
    ),
}


class CurrentCoverageV24Error(_v23.CurrentCoverageV23Error):
    """Raised when the v24 preparation or publication contract fails closed."""


class PendingDownstreamPinsError(CurrentCoverageV24Error):
    """Raised while a downstream replacement or publication fuse is unresolved."""


@dataclass(frozen=True)
class CurrentCoverageV24Bundle:
    ledger_bytes: bytes
    manifest_bytes: bytes
    manifest_hash_bytes: bytes
    ledger: Mapping[str, Any]
    manifest: Mapping[str, Any]


@dataclass(frozen=True)
class _PreparedV24Publication:
    bundle_identity: tuple[int, int]
    bundle_member_identities: Mapping[str, tuple[int, int]]
    bundle_stage: Path
    bundle_tree_sha256: str
    definition_identity: tuple[int, int]
    definition_raw: bytes
    definition_stage: Path
    generated_at: datetime


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_line(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _component_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        digest.update(_canonical_line(entry))
    return digest.hexdigest()


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CurrentCoverageV24Error(f"{label} must be canonical UTC seconds")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CurrentCoverageV24Error(f"{label} is invalid") from error
    canonical = parsed.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    if value != canonical:
        raise CurrentCoverageV24Error(f"{label} must be canonical UTC seconds")
    return parsed.astimezone(UTC)


def _parse_pinned_source_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CurrentCoverageV24Error(f"{label} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as error:
        raise CurrentCoverageV24Error(f"{label} is invalid") from error
    canonical_seconds = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    canonical_microseconds = parsed.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    if value not in {canonical_seconds, canonical_microseconds}:
        raise CurrentCoverageV24Error(f"{label} must be canonical UTC")
    return parsed


def _read_json(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise CurrentCoverageV24Error(f"{label} must be a regular file: {path}")
    raw = path.read_bytes()
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CurrentCoverageV24Error(f"{label} is not valid JSON") from error
    if not isinstance(document, dict) or raw != _canonical_json(document):
        raise CurrentCoverageV24Error(f"{label} is not canonical JSON")
    return raw, document


def _inside(package_root: Path, relative: str, label: str) -> Path:
    candidate = package_root / relative
    resolved = candidate.resolve()
    try:
        resolved.relative_to(package_root)
    except ValueError as error:
        raise CurrentCoverageV24Error(f"{label} escapes package root") from error
    return candidate


def _tree_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise CurrentCoverageV24Error(f"accepted tree is not a regular directory: {root}")
    digest = hashlib.sha256()
    paths = [
        root,
        *sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix()),
    ]
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise CurrentCoverageV24Error(f"accepted tree contains symlink: {path}")
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_dir():
            digest.update(f"D\0{relative}\0{mode:04o}\n".encode())
        elif path.is_file():
            raw = path.read_bytes()
            digest.update(
                (
                    f"F\0{relative}\0{mode:04o}\0{len(raw)}\0"
                    f"{_sha256(raw)}\n"
                ).encode()
            )
        else:
            raise CurrentCoverageV24Error(f"accepted tree entry is unsupported: {path}")
    return digest.hexdigest()


def _load_v23_base(package_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for label, spec in (
        ("definition", V23_BASE_LINEAGE["definition"]),
        ("ledger", V23_BASE_LINEAGE["ledger"]),
        ("manifest", V23_BASE_LINEAGE["manifest"]),
    ):
        path = _inside(package_root, str(spec["path"]), f"v23 {label}")
        raw, document = _read_json(path, f"v23 {label}")
        if len(raw) != spec["bytes"] or _sha256(raw) != spec["sha256"]:
            raise CurrentCoverageV24Error(f"accepted v23 {label} pin changed")
        documents[label] = document
    sidecar = _inside(
        package_root, str(V23_SIDECAR["path"]), "accepted v23 sidecar"
    )
    if sidecar.is_symlink() or not sidecar.is_file():
        raise CurrentCoverageV24Error("accepted v23 sidecar is not regular")
    sidecar_raw = sidecar.read_bytes()
    if (
        len(sidecar_raw) != V23_SIDECAR["bytes"]
        or _sha256(sidecar_raw) != V23_SIDECAR["sha256"]
    ):
        raise CurrentCoverageV24Error("accepted v23 sidecar pin changed")
    bundle = package_root / "current_coverage_ledgers/2026-07-21-v23"
    if _tree_digest(bundle) != V23_BUNDLE_TREE_SHA256:
        raise CurrentCoverageV24Error("accepted v23 bundle tree changed")
    if documents["definition"].get("ledger_id") != V23_BASE_LINEAGE["ledger_id"]:
        raise CurrentCoverageV24Error("accepted v23 definition identity changed")
    if documents["ledger"].get("ledger_id") != V23_BASE_LINEAGE["ledger_id"]:
        raise CurrentCoverageV24Error("accepted v23 ledger identity changed")
    return documents["definition"], documents["ledger"]


def _checkpoint(
    checkpoint_id: str,
    path: str,
    byte_count: int,
    sha256: str,
    *,
    binding: tuple[str, str] | None = None,
) -> dict[str, Any]:
    return _v22._checkpoint(
        checkpoint_id, path, byte_count, sha256, binding=binding
    )


def _metric(
    label: str, checkpoint_id: str, pointer: str, value: Any
) -> dict[str, Any]:
    return _v22._metric(label, checkpoint_id, pointer, value)


def _replacement(
    base_entries: Mapping[str, Mapping[str, Any]],
    previous_id: str,
    new_id: str,
    *,
    checkpoints: list[dict[str, Any]],
    limitations: list[str],
    metrics: list[dict[str, Any]],
    record_units: list[str] | None = None,
) -> dict[str, Any]:
    entry = deepcopy(dict(base_entries[previous_id]))
    entry["artifact_id"] = new_id
    entry["checkpoints"] = checkpoints
    entry["limitations"] = limitations
    entry["metrics"] = metrics
    if record_units is not None:
        entry["record_units"] = sorted(record_units)
    return entry


def _accepted_replacement_entries(
    base_entries: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    construction_map = _replacement(
        base_entries,
        "construction-map-public-open-v29",
        "construction-map-public-open-v30",
        checkpoints=[
            _checkpoint(
                "coverage",
                "construction_maps/2026-07-21-public-open-v30/coverage.json",
                7_524,
                "bb4eeb2cfafdc50e0b1fedf21feee4fdef399b7ddc460306b7cb0f128b48b61f",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-map-2026-07-21-public-open-v30.json",
                2_442,
                "47f2322edd2983bc8ed881edf8e0071d806df304cf773be2e215bcc1806d0847",
            ),
            _checkpoint(
                "manifest",
                "construction_maps/2026-07-21-public-open-v30/manifest.json",
                2_192,
                "73108a00068912f83233114fc2ab7ae79087e610d54226762512fe3cc8ef4360",
            ),
        ],
        limitations=[
            "Map rows are a presentation derivative of construction-master v30 and must never be added to the master-row total.",
            "Mapped observations include unpromoted review and discovery rows and are not unique physical sites.",
            "Three hundred seventy-two master observations lack coordinates, including 354 Tier-A rows; another 102,541 mapped observations retain an unknown country label.",
        ],
        metrics=[
            _metric(
                "added_replacement_rows_unmapped",
                "coverage",
                "/projection/added_replacement_rows_unmapped",
                243,
            ),
            _metric(
                "default_visible_rows",
                "definition",
                "/expected_projection/default_visible_rows",
                6_508,
            ),
            _metric(
                "mapped_replacement_rows",
                "coverage",
                "/counts/mapped_replacement_rows",
                109,
            ),
            _metric(
                "mapped_rows_with_any_role",
                "coverage",
                "/counts/mapped_rows_with_any_role",
                78,
            ),
            _metric(
                "mapped_tier_a_rows",
                "coverage",
                "/mapped_counts/by_tier/A",
                228,
            ),
            _metric(
                "mapped_tier_b_rows",
                "coverage",
                "/mapped_counts/by_tier/B",
                6_280,
            ),
            _metric(
                "mapped_tier_c_rows",
                "coverage",
                "/mapped_counts/by_tier/C",
                102_494,
            ),
            _metric(
                "mapped_total_rows",
                "coverage",
                "/counts/mapped_observation_rows",
                109_002,
            ),
            _metric(
                "mapped_unknown_country_rows",
                "coverage",
                "/mapped_counts/by_country/Unknown",
                102_541,
            ),
            _metric(
                "master_total_rows",
                "coverage",
                "/counts/master_observation_rows",
                109_374,
            ),
            _metric(
                "unique_physical_sites",
                "coverage",
                "/counts/unique_physical_site_count",
                None,
            ),
            _metric(
                "unmapped_rows",
                "coverage",
                "/counts/unmapped_observation_rows",
                372,
            ),
        ],
    )
    master = _replacement(
        base_entries,
        "construction-master-public-open-v29",
        "construction-master-public-open-v30",
        checkpoints=[
            _checkpoint(
                "coverage",
                "construction_master/2026-07-21-public-open-v30/coverage.json",
                8_550,
                "db046e49a5590fdbae810343d9efa9d4f34401a2c2bfdb513d8c552d8507a5aa",
                binding=("manifest", "/outputs/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-master-2026-07-21-public-open-v30.json",
                5_659,
                "981bfd4dcf9bcb6f00f6825c4ac74d62b2bfefeb019fbfa945b774c136683a63",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "construction_master/2026-07-21-public-open-v30/manifest.json",
                9_720,
                "8f81ded9c9f351caa0f7a75afce8b4a7abe673c3a078c5bf5fd7bb1f75eabf1f",
            ),
        ],
        limitations=[
            "Capacity observations preserve source type and stage and are not globally additive; no annual energy is inferred from power or capacity.",
            "Historical lifecycle statuses, including 449 source-normalized under_construction rows, are source-scoped last-observed facts and do not establish current construction after reported_status_date.",
            "Only 582 Tier-A source-supported observation rows enter construction arithmetic; the 109,374 total includes review and structural-discovery rows and is not a unique-site count.",
            "Planning, permit, environmental-opinion, fuzzy, SEC, imagery-review, and structural-candidate records remain separate review units and are not added to construction arithmetic.",
            "The accepted Unknown033 recovery contributes four control-plane files and zero rows; its payload is not traversed and its imagery creates no inference.",
        ],
        metrics=[
            _metric(
                "added_replacement_rows",
                "coverage",
                "/replacement_invariants/added_replacement_rows",
                263,
            ),
            _metric(
                "base_rows",
                "coverage",
                "/replacement_invariants/base_rows",
                109_111,
            ),
            _metric(
                "contract_marked_rows",
                "coverage",
                "/replacement_invariants/rows_with_contract_marker",
                462,
            ),
            _metric(
                "inherited_rows",
                "coverage",
                "/replacement_invariants/inherited_rows",
                108_912,
            ),
            _metric(
                "publication_contract_version",
                "coverage",
                "/replacement/publication_contract_version",
                4,
            ),
            _metric(
                "replacement_rows",
                "coverage",
                "/replacement_invariants/replacement_rows",
                462,
            ),
            _metric(
                "role_rows_with_any_role",
                "coverage",
                "/role_counts/rows_with_any_role",
                179,
            ),
            _metric(
                "role_rows_with_customers",
                "coverage",
                "/role_counts/with_core_role/customers",
                2,
            ),
            _metric(
                "role_rows_with_operator",
                "coverage",
                "/role_counts/with_core_role/operator",
                82,
            ),
            _metric(
                "role_rows_with_owner",
                "coverage",
                "/role_counts/with_core_role/owner",
                53,
            ),
            _metric(
                "role_rows_with_source_role_tags",
                "coverage",
                "/role_counts/rows_with_source_role_tags",
                140,
            ),
            _metric(
                "role_rows_with_tenants",
                "coverage",
                "/role_counts/with_core_role/tenants",
                7,
            ),
            _metric(
                "role_rows_with_users",
                "coverage",
                "/role_counts/with_core_role/users",
                37,
            ),
            _metric(
                "satellite_recovery_control_plane_bytes",
                "coverage",
                "/satellite_recovery_acceptance/control_plane_bytes",
                15_313,
            ),
            _metric(
                "satellite_recovery_control_plane_files",
                "coverage",
                "/satellite_recovery_acceptance/control_plane_files",
                4,
            ),
            _metric(
                "satellite_recovery_rows",
                "coverage",
                "/satellite_recovery_acceptance/rows_created",
                0,
            ),
            _metric(
                "status_under_construction_rows",
                "coverage",
                "/row_counts/by_normalized_status/under_construction",
                449,
            ),
            _metric("tier_a_rows", "coverage", "/row_counts/by_tier/A", 582),
            _metric("tier_b_rows", "coverage", "/row_counts/by_tier/B", 6_298),
            _metric(
                "tier_c_rows", "coverage", "/row_counts/by_tier/C", 102_494
            ),
            _metric(
                "total_master_rows", "coverage", "/row_counts/total", 109_374
            ),
            _metric(
                "unchanged_replacement_rows",
                "coverage",
                "/replacement_invariants/unchanged_replacement_rows",
                199,
            ),
            _metric(
                "unique_physical_sites",
                "coverage",
                "/row_counts/unique_physical_site_count",
                None,
            ),
        ],
    )
    coverage = _replacement(
        base_entries,
        "coverage-audit-public-open-v29",
        "coverage-audit-public-open-v30",
        checkpoints=[
            _checkpoint(
                "manifest",
                "audits/2026-07-21-public-open-coverage-v30/manifest.json",
                3_379,
                "5bd7257085f52258c5187f38f811148e8edb9a38d212fc44104f9368bf769b78",
            )
        ],
        limitations=[
            "Gap counts audit source-scoped rows and review rows without computing unique physical sites.",
            "The 946 source and source-country groups and 4,469 open gaps are coverage-accounting units, not site counts.",
            "The satellite methodology-support artifact is non-countable review support and creates no facility, lifecycle, identity, status, or capacity claim.",
        ],
        metrics=[
            _metric("coverage_groups", "manifest", "/counts/coverage_groups", 946),
            _metric(
                "methodology_support_artifacts",
                "manifest",
                "/counts/methodology_support_artifacts",
                1,
            ),
            _metric(
                "methodology_support_jobs",
                "manifest",
                "/counts/methodology_support_jobs",
                74,
            ),
            _metric(
                "methodology_support_views",
                "manifest",
                "/counts/methodology_support_views",
                71,
            ),
            _metric(
                "non_review_source_scoped_rows",
                "manifest",
                "/counts/non_review_source_scoped_entity_records",
                10_200,
            ),
            _metric("open_gaps", "manifest", "/counts/open_gaps", 4_469),
            _metric(
                "review_only_source_scoped_rows",
                "manifest",
                "/counts/review_only_source_scoped_entity_records",
                6_130,
            ),
            _metric(
                "source_scoped_rows",
                "manifest",
                "/counts/source_scoped_entity_records",
                16_330,
            ),
            _metric(
                "unique_physical_sites",
                "manifest",
                "/counts/unique_physical_sites",
                None,
            ),
        ],
    )
    federation = _replacement(
        base_entries,
        "federation-public-open-v33",
        "federation-public-open-v34",
        checkpoints=[
            _checkpoint(
                "index",
                "federated_indexes/2026-07-21-public-open-v34/federated-index.json",
                35_181,
                "6389e18f6a1085e0a2cba577e412406187ea89d017e921aba6e7fb3edede60ba",
                binding=("manifest", "/artifacts/federated-index.json"),
            ),
            _checkpoint(
                "manifest",
                "federated_indexes/2026-07-21-public-open-v34/manifest.json",
                986,
                "31f2d60f266045f01af510f9fc16e541642231697167f3feaf3a70012a376503",
            ),
        ],
        limitations=[
            "Historical lifecycle observations are last-observed facts and do not establish current construction without later evidence.",
            "The 16,330 source-scoped rows are an arithmetic sum across three child releases, not unique physical sites.",
            "The 6,712 construction-pipeline records include 6,130 review-only fuzzy rows and only 582 non-review observations; they are not all confirmed construction sites.",
        ],
        metrics=[
            _metric(
                "capacity_observations",
                "index",
                "/counts/capacity_estimates",
                1_328,
            ),
            _metric(
                "construction_pipeline_records",
                "index",
                "/counts/construction_pipeline_records",
                6_712,
            ),
            _metric(
                "non_review_construction_pipeline_records",
                "index",
                "/counts/non_review_construction_pipeline_records",
                582,
            ),
            _metric(
                "non_review_source_scoped_rows",
                "index",
                "/counts/non_review_source_scoped_entity_records",
                10_200,
            ),
            _metric(
                "review_only_construction_pipeline_records",
                "index",
                "/counts/review_only_construction_pipeline_records",
                6_130,
            ),
            _metric(
                "review_only_source_scoped_rows",
                "index",
                "/counts/review_only_source_scoped_entity_records",
                6_130,
            ),
            _metric(
                "source_scoped_rows",
                "index",
                "/counts/source_scoped_entity_records",
                16_330,
            ),
            _metric(
                "unique_physical_sites",
                "index",
                "/counts/unique_physical_sites",
                None,
            ),
        ],
    )
    identity = _replacement(
        base_entries,
        "exact-identity-decisions-public-open-v9",
        "exact-identity-decisions-public-open-v10",
        checkpoints=[
            _checkpoint(
                "accounting",
                "exact_identity_decisions/2026-07-21-public-open-v10/accounting.json",
                981,
                "fc9c2b08983b785b3f5792068dd9b80262f2fa1bbf6dd1496dd7a6cb73b45794",
                binding=("manifest", "/files/accounting.json"),
            ),
            _checkpoint(
                "definition",
                "sources/exact-identity-decisions-2026-07-21-public-open-v10.json",
                1_736,
                "b68c6cd6f84405844b518dcf1aa421f86202c7d2f86c1325905333e5f281d78b",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "exact_identity_decisions/2026-07-21-public-open-v10/manifest.json",
                11_441,
                "5806448df1316aa56e4ba82a63961f5dd0b6337ee455de29929c369288a940fe",
            ),
        ],
        limitations=deepcopy(
            base_entries["exact-identity-decisions-public-open-v9"]["limitations"]
        ),
        metrics=[
            _metric(
                "ambiguous_identity_candidate_references",
                "accounting",
                "/ambiguous_identity_candidate_references",
                127,
            ),
            _metric(
                "canonical_topology_links",
                "accounting",
                "/canonical_topology_links",
                2_440,
            ),
            _metric(
                "exact_component_reductions",
                "accounting",
                "/exact_component_reductions",
                1_732,
            ),
            _metric(
                "exact_source_record_components",
                "accounting",
                "/exact_source_record_components",
                8_468,
            ),
            _metric(
                "non_review_source_scoped_rows",
                "accounting",
                "/non_review_source_scoped_entity_records",
                10_200,
            ),
            _metric(
                "physical_site_lower_bound",
                "accounting",
                "/physical_site_lower_bound",
                None,
            ),
            _metric(
                "physical_site_upper_bound",
                "accounting",
                "/physical_site_upper_bound",
                None,
            ),
            _metric(
                "raw_topology_links", "accounting", "/raw_topology_links", 2_845
            ),
            _metric(
                "release_candidate_references",
                "accounting",
                "/release_candidate_references",
                100_412,
            ),
            _metric(
                "review_only_rows_in_public_accounting",
                "manifest",
                "/scope/review_only_rows_in_public_accounting",
                False,
            ),
            _metric(
                "source_scoped_entity_rows",
                "accounting",
                "/source_scoped_entity_records",
                16_330,
            ),
            _metric(
                "unique_physical_sites",
                "accounting",
                "/unique_physical_sites",
                None,
            ),
            _metric(
                "unresolved_candidate_references",
                "accounting",
                "/unresolved_candidate_references",
                100_539,
            ),
        ],
    )
    seed = _replacement(
        base_entries,
        "seed-epoch-official-v73",
        "seed-epoch-official-v83",
        checkpoints=[
            _checkpoint(
                "manifest",
                "releases/2026-07-21-open-seed-v83/manifest.json",
                14_812,
                "56f33ade743f50e36bd4b2d6f32fa71eaa2b117af79c8580f92d7319c77bd7d5",
            )
        ],
        limitations=[
            "Capacity observations preserve their source-declared type and stage and are not globally additive; no annual energy is inferred.",
            "Status, type, role, workload, capacity, energy, and PUE fields remain source-scoped; last-observed status is not current status and absent fields are not inferred from satellite imagery.",
            "The 506 freshness rows are non-additive with timeline v7 and classify current status as unknown rather than asserting current construction.",
            "The 905 source-scoped entity rows comprise 474 campus observations and 431 project observations, not deduplicated physical sites.",
        ],
        metrics=[
            _metric("campus_rows", "manifest", "/entities_by_kind/campus", 474),
            _metric(
                "capacity_observations", "manifest", "/capacity_estimates", 542
            ),
            _metric(
                "construction_pipeline_records",
                "manifest",
                "/construction_pipeline_records",
                462,
            ),
            _metric(
                "construction_source_signals",
                "manifest",
                "/construction_source_signals",
                364,
            ),
            _metric(
                "current_status_inferred",
                "manifest",
                "/current_status_inferred",
                False,
            ),
            _metric("evidence_records", "manifest", "/evidence_records", 586),
            _metric(
                "lifecycle_freshness_records",
                "manifest",
                "/lifecycle_freshness_records",
                506,
            ),
            _metric(
                "lifecycle_status_semantics",
                "manifest",
                "/lifecycle_status_semantics",
                "last_observed",
            ),
            _metric("project_rows", "manifest", "/entities_by_kind/project", 431),
            _metric(
                "publication_contract_version",
                "manifest",
                "/publication_contract_version",
                4,
            ),
            _metric(
                "resolution_candidates", "manifest", "/resolution_candidates", 7
            ),
            _metric(
                "source_scoped_entity_rows", "manifest", "/entities", 905
            ),
        ],
        record_units=[
            "capacity_observation",
            "construction_pipeline_record",
            "lifecycle_observation",
            "source_scoped_entity_row",
        ],
    )
    timeline = _replacement(
        base_entries,
        "construction-timeline-public-open-v6",
        "construction-timeline-public-open-v7",
        checkpoints=[
            _checkpoint(
                "coverage",
                "construction_timelines/2026-07-21-public-open-v7/coverage.json",
                68_483,
                "45246273b5a84287a4da3633fa9dbb437f97976be23731f5998fd0f763c12c60",
                binding=("manifest", "/files/coverage.json"),
            ),
            _checkpoint(
                "definition",
                "sources/construction-timeline-2026-07-21-public-open-v7.json",
                2_941,
                "2fa593cbb2f135e1e6feb5baf3e18efa0fd4b9a88a4b264884306a50e43aece1",
                binding=("manifest", "/definition"),
            ),
            _checkpoint(
                "manifest",
                "construction_timelines/2026-07-21-public-open-v7/manifest.json",
                3_897,
                "a5378eb55f42132193d1e82b97dec5a252e950fa5c4d0c22b278c404ad921265",
            ),
        ],
        limitations=[
            "Dated raw observations and last-observed statuses do not establish current construction; all 506 timeline current-status classifications remain unknown and current_construction_claimed is false.",
            "No interpolation, forecast conversion, persistence assumption, quarterly parity, cross-source identity resolution, or satellite lifecycle promotion is applied.",
            "The 526 lifecycle observations across 506 source-scoped timelines and 244 source families are not cross-source-deduplicated unique physical sites.",
            "The STT Johor under-construction observation is a stale historical fact dated 2025-02-24, not a current construction classification.",
        ],
        metrics=[
            _metric(
                "current_construction_claimed",
                "coverage",
                "/scope/current_construction_claimed",
                False,
            ),
            _metric(
                "current_status_classification",
                "coverage",
                "/scope/current_status_classification",
                "unknown",
            ),
            _metric(
                "entities_with_lifecycle_observations",
                "coverage",
                "/counts/entities_with_lifecycle_observations",
                506,
            ),
            _metric(
                "raw_lifecycle_observations",
                "coverage",
                "/counts/raw_lifecycle_observations",
                526,
            ),
            _metric(
                "source_families", "coverage", "/counts/source_families", 244
            ),
            _metric(
                "stt_current_construction_claim",
                "coverage",
                "/stt_johor_historical_only/current_construction_claim",
                False,
            ),
            _metric(
                "stt_freshness_class",
                "coverage",
                "/stt_johor_historical_only/freshness_class",
                "stale_over_365_days",
            ),
            _metric(
                "stt_observation_age_days",
                "coverage",
                "/stt_johor_historical_only/observation_age_days",
                512,
            ),
            _metric(
                "stt_status",
                "coverage",
                "/stt_johor_historical_only/status",
                "under_construction",
            ),
            _metric(
                "unique_physical_sites",
                "coverage",
                "/scope/unique_physical_sites",
                None,
            ),
        ],
    )
    queue = _replacement(
        base_entries,
        "satellite-queue-open-seed-v71",
        "satellite-queue-open-seed-v83",
        checkpoints=[
            _checkpoint(
                "manifest",
                "satellite_review_queues/2026-07-21-open-seed-v83/manifest.json",
                19_851,
                "cd31436eb4bc862096952403d70be33ed41d0e752a3a617ce2d175569049c9bd",
            ),
            _checkpoint(
                "release_manifest",
                "releases/2026-07-21-open-seed-v83/manifest.json",
                14_812,
                "56f33ade743f50e36bd4b2d6f32fa71eaa2b117af79c8580f92d7319c77bd7d5",
                binding=("manifest", "/source/release_manifest"),
            ),
        ],
        limitations=[
            "Queue jobs are review plans for source-scoped seed-v83 observations, not deduplicated sites, imagery findings, or current construction evidence.",
            "The active-construction priority tier is derived from last-observed source status and does not establish that any of its 104 queued observations remains under construction now.",
            "The historical seed-v71 catalog and analyst-review contracts are not coverage of this v83 queue.",
            "The queue is non-additive with seed v83; 705 coordinate-null seed-v83 observations remain outside imagery execution.",
        ],
        metrics=[
            _metric(
                "active_construction_priority_jobs",
                "manifest",
                "/counts/queued_entities_by_priority_tier/active_construction",
                104,
            ),
            _metric(
                "entities_queued", "manifest", "/counts/entities_queued", 200
            ),
            _metric(
                "network_requests_performed",
                "manifest",
                "/scope/network_requests_performed",
                False,
            ),
            _metric(
                "operational_priority_jobs",
                "manifest",
                "/counts/queued_entities_by_priority_tier/operational",
                29,
            ),
            _metric(
                "proposed_pipeline_priority_jobs",
                "manifest",
                "/counts/queued_entities_by_priority_tier/proposed_pipeline",
                5,
            ),
            _metric("queue_jobs", "manifest", "/counts/queue_jobs", 200),
            _metric(
                "skipped_missing_coordinates",
                "manifest",
                "/counts/skipped_missing_coordinates",
                705,
            ),
            _metric(
                "unknown_priority_jobs",
                "manifest",
                "/counts/queued_entities_by_priority_tier/unknown",
                62,
            ),
        ],
    )
    return {
        construction_map["artifact_id"]: construction_map,
        master["artifact_id"]: master,
        coverage["artifact_id"]: coverage,
        federation["artifact_id"]: federation,
        identity["artifact_id"]: identity,
        queue["artifact_id"]: queue,
        seed["artifact_id"]: seed,
        timeline["artifact_id"]: timeline,
    }


def _review_entry(
    *,
    artifact_id: str,
    artifact_kind: str,
    checkpoints: list[dict[str, Any]],
    limitations: list[str],
    metrics: list[dict[str, Any]],
    record_units: list[str],
) -> dict[str, Any]:
    return {
        "access_tier": "public_open",
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "checkpoints": checkpoints,
        "current_role": "public_supporting_review_lane",
        "evidence_scope": "review_only",
        "limitations": sorted(limitations),
        "metrics": metrics,
        "publication_mode": "public_review_or_discovery",
        "record_units": sorted(record_units),
        "redistribution_status": "eligible_with_upstream_terms",
    }


def _v23_addition_entry_shape_reference() -> dict[str, dict[str, Any]]:
    # Retained as a non-executed reference for the accepted v23 contract shape.
    catalog = _review_entry(
        artifact_id="satellite-catalog-open-seed-v71-active-explicit-final-v1",
        artifact_kind="satellite_catalog_batch",
        checkpoints=[
            _checkpoint(
                "manifest",
                "satellite_review_runs/"
                "2026-07-21-open-seed-v71-active-explicit-final-v1/"
                "batch-manifest.json",
                64_864,
                "c930e7a0431540ead5fe54d8cc60808bc0e1e8a57ddea99acb01eacb94d25da9",
            ),
            _checkpoint(
                "queue_manifest",
                "satellite_review_queues/2026-07-21-open-seed-v71/manifest.json",
                17_073,
                "e62b514acc196c4a1318907b3509676542798ac5da89fda304f5485e0cfd1000",
            ),
            _checkpoint(
                "selection_receipt",
                "satellite_review_runs/"
                "2026-07-21-open-seed-v71-active-explicit-final-v1/"
                "selection-receipt.json",
                9_921,
                "cab75bcfb893002baa65a04bd3e2b1a104a510cf820076f7fcddecb5a2c665d2",
                binding=("manifest", "/selection_receipt"),
            ),
        ],
        limitations=[
            "Catalog availability and selected scene IDs are review controls, not visible-change, identity, lifecycle, operating-status, type, capacity, power, energy, PUE, workload, or unique-site evidence.",
            "The batch represents 98 active-priority queue jobs but executes only the 11 immutable receipt IDs; the other 87 remain pending and all counts are non-additive with the v71 queue.",
            "The finalized tree is a frozen byte-identical copy of the mutable execution checkpoint; no change analysis or Atlas mutation was performed by this catalog-only contract.",
        ],
        metrics=[
            _metric(
                "atlas_mutation",
                "manifest",
                "/scope/atlas_mutation",
                False,
            ),
            _metric(
                "change_analysis_executed",
                "manifest",
                "/scope/change_analysis_executed",
                False,
            ),
            _metric(
                "jobs_completed", "manifest", "/summary/jobs_completed", 11
            ),
            _metric(
                "jobs_failed", "manifest", "/summary/jobs_failed", 0
            ),
            _metric(
                "jobs_not_selected",
                "manifest",
                "/summary/jobs_not_selected",
                87,
            ),
            _metric(
                "jobs_pending", "manifest", "/summary/jobs_pending", 87
            ),
            _metric(
                "jobs_represented",
                "manifest",
                "/summary/jobs_represented",
                98,
            ),
            _metric(
                "jobs_selected_for_execution",
                "manifest",
                "/summary/jobs_selected_for_execution",
                11,
            ),
            _metric(
                "review_required", "manifest", "/scope/review_required", True
            ),
            _metric(
                "selected_jobs_unavailable_no_scene",
                "manifest",
                "/summary/selected_jobs_unavailable_no_scene",
                0,
            ),
            _metric(
                "unexpected_output_adoption",
                "manifest",
                "/scope/unexpected_output_adoption",
                False,
            ),
        ],
        record_units=["catalog_job", "catalog_link"],
    )
    queue = _review_entry(
        artifact_id="satellite-queue-open-seed-v71",
        artifact_kind="satellite_review_queue",
        checkpoints=[
            _checkpoint(
                "manifest",
                "satellite_review_queues/2026-07-21-open-seed-v71/manifest.json",
                17_073,
                "e62b514acc196c4a1318907b3509676542798ac5da89fda304f5485e0cfd1000",
            ),
            _checkpoint(
                "release_manifest",
                "releases/2026-07-21-open-seed-v71/manifest.json",
                12_577,
                "0f8acbce360f763707cb4c51276a0873ee60ec96d9258b1915fa8c76fcf9fa22",
                binding=("manifest", "/source/release_manifest"),
            ),
        ],
        limitations=[
            "Queue jobs are review plans for source-scoped seed-v71 observations, not deduplicated sites, imagery findings, or current construction evidence.",
            "The active-construction priority tier is derived from last-observed source status and does not establish that any of its 98 queued observations remains under construction now.",
            "The queue is non-additive with seed v73 and the explicit catalog selection; 621 coordinate-null seed-v71 observations remain outside imagery execution.",
        ],
        metrics=[
            _metric(
                "active_construction_priority_jobs",
                "manifest",
                "/counts/queued_entities_by_priority_tier/active_construction",
                98,
            ),
            _metric(
                "entities_queued", "manifest", "/counts/entities_queued", 189
            ),
            _metric(
                "network_requests_performed",
                "manifest",
                "/scope/network_requests_performed",
                False,
            ),
            _metric(
                "operational_priority_jobs",
                "manifest",
                "/counts/queued_entities_by_priority_tier/operational",
                29,
            ),
            _metric(
                "proposed_pipeline_priority_jobs",
                "manifest",
                "/counts/queued_entities_by_priority_tier/proposed_pipeline",
                5,
            ),
            _metric("queue_jobs", "manifest", "/counts/queue_jobs", 189),
            _metric(
                "skipped_missing_coordinates",
                "manifest",
                "/counts/skipped_missing_coordinates",
                621,
            ),
            _metric(
                "unknown_priority_jobs",
                "manifest",
                "/counts/queued_entities_by_priority_tier/unknown",
                57,
            ),
        ],
        record_units=["catalog_job"],
    )
    analyst_review = _review_entry(
        artifact_id=(
            "satellite-change-review-open-seed-v71-active-explicit-11-review-v1"
        ),
        artifact_kind="analyst_imagery_review",
        checkpoints=[
            _checkpoint(
                "blind_decisions",
                "satellite_change_reviews/"
                "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
                "blind-decisions.json",
                6_890,
                "6e6bc074400b13d47c23953c2224ab50e12b4b6f2b48a1377237275b3edde0eb",
                binding=("manifest", "/artifacts/blind-decisions.json"),
            ),
            _checkpoint(
                "definition",
                "satellite_change_reviews/"
                "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
                "definition.json",
                4_158,
                "b2e6acbd705f4d0229222bfa0e6d17532e3866225315280c578933e00bbd3ff2",
                binding=("manifest", "/artifacts/definition.json"),
            ),
            _checkpoint(
                "manifest",
                "satellite_change_reviews/"
                "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
                "manifest.json",
                4_203,
                "d5184c13eca93b9f07711781665deca71d271ec263627437285e813cdb495b12",
            ),
            _checkpoint(
                "summary",
                "satellite_change_reviews/"
                "2026-07-21-open-seed-v71-active-explicit-11-review-v1/"
                "summary.json",
                3_352,
                "ccdc4ae77e550073469c8b1672d961e7be8a7e26ca4c1d782926effd3e6afeef",
                binding=("manifest", "/artifacts/summary.json"),
            ),
        ],
        limitations=[
            "The eleven identity-blind decisions retain seven image pairs for manual visible-change follow-up and reject four for site promotion; neither disposition establishes or negates construction, lifecycle, operating status, or any separately sourced fact.",
            "The four ambiguous decisions, one temporal-metadata correction, and two reciprocal visual-identity links remain review controls and do not create a unique-site count or cross-source identity resolution.",
            "The 44 inspected visuals and 66 hash-bound source artifacts are non-additive review records; imagery and change-mask metadata create no atlas mutation, automated promotion, data-centre type, capacity, power, energy, PUE, operator, or workload claim.",
        ],
        metrics=[
            _metric(
                "analyst_decisions", "manifest", "/summary/analyst_decisions", 11
            ),
            _metric("atlas_mutation", "manifest", "/guardrails/atlas_mutation", False),
            _metric(
                "automated_promotion_allowed",
                "manifest",
                "/guardrails/automated_promotion_allowed",
                False,
            ),
            _metric(
                "capacity_claim_created",
                "manifest",
                "/guardrails/capacity_claim_created",
                False,
            ),
            _metric(
                "construction_status_claim_created",
                "manifest",
                "/guardrails/construction_status_claim_created",
                False,
            ),
            _metric(
                "current_status_claim_created",
                "manifest",
                "/guardrails/current_status_claim_created",
                False,
            ),
            _metric(
                "data_centre_identity_claim_created",
                "manifest",
                "/guardrails/data_centre_identity_claim_created",
                False,
            ),
            _metric(
                "data_centre_type_claim_created",
                "manifest",
                "/guardrails/data_centre_type_claim_created",
                False,
            ),
            _metric(
                "energy_claim_created",
                "manifest",
                "/guardrails/energy_claim_created",
                False,
            ),
            _metric(
                "image_quality_partially_obscured",
                "manifest",
                "/summary/image_quality/partially_obscured",
                4,
            ),
            _metric(
                "image_quality_usable",
                "manifest",
                "/summary/image_quality/usable",
                7,
            ),
            _metric(
                "imagery_construction_truth_claim_created",
                "manifest",
                "/guardrails/imagery_construction_truth_claim_created",
                False,
            ),
            _metric(
                "it_capacity_claim_created",
                "manifest",
                "/guardrails/it_capacity_claim_created",
                False,
            ),
            _metric(
                "lifecycle_status_claim_created",
                "manifest",
                "/guardrails/lifecycle_status_claim_created",
                False,
            ),
            _metric(
                "operator_claim_created",
                "manifest",
                "/guardrails/operator_claim_created",
                False,
            ),
            _metric(
                "power_claim_created",
                "manifest",
                "/guardrails/power_claim_created",
                False,
            ),
            _metric(
                "promotion_rejected",
                "manifest",
                "/summary/promotion_dispositions/rejected_for_site_promotion",
                4,
            ),
            _metric(
                "promotion_retained_for_manual_followup",
                "manifest",
                "/summary/promotion_dispositions/retained_for_manual_followup",
                7,
            ),
            _metric(
                "pue_claim_created",
                "manifest",
                "/guardrails/pue_claim_created",
                False,
            ),
            _metric(
                "site_count_claim_created",
                "manifest",
                "/guardrails/site_count_claim_created",
                False,
            ),
            _metric(
                "source_artifacts_hash_bound",
                "manifest",
                "/summary/source_artifacts_hash_bound",
                66,
            ),
            _metric(
                "temporal_metadata_corrections",
                "manifest",
                "/summary/temporal_metadata_corrections",
                1,
            ),
            _metric(
                "unique_site_claim_created",
                "manifest",
                "/guardrails/unique_site_claim_created",
                False,
            ),
            _metric(
                "visible_change_ambiguous",
                "manifest",
                "/summary/visible_change/ambiguous",
                4,
            ),
            _metric(
                "visible_change_clear",
                "manifest",
                "/summary/visible_change/clear",
                7,
            ),
            _metric(
                "visual_artifacts_inspected",
                "manifest",
                "/summary/visual_artifacts_inspected",
                44,
            ),
            _metric(
                "visual_identity_links",
                "manifest",
                "/summary/visual_identity_links",
                2,
            ),
            _metric(
                "workload_claim_created",
                "manifest",
                "/guardrails/workload_claim_created",
                False,
            ),
        ],
        record_units=["aggregate_report_metric", "review_record"],
    )
    return {
        analyst_review["artifact_id"]: analyst_review,
        catalog["artifact_id"]: catalog,
        queue["artifact_id"]: queue,
    }


def _accepted_addition_entries() -> dict[str, dict[str, Any]]:
    catalog = _review_entry(
        artifact_id=(
            "satellite-catalog-open-seed-v83-active-explicit-"
            "new-projects-final-v1"
        ),
        artifact_kind="satellite_catalog_batch",
        checkpoints=[
            _checkpoint(
                "manifest",
                "satellite_review_runs/"
                "2026-07-21-open-seed-v83-active-explicit-"
                "new-projects-final-v1/batch-manifest.json",
                65_077,
                "d8c99c8cd5f82f8474c4f7f0ab0ef5b002555583d083b6664ed5ae600b477a48",
            ),
            _checkpoint(
                "queue_manifest",
                "satellite_review_queues/2026-07-21-open-seed-v83/manifest.json",
                19_851,
                "cd31436eb4bc862096952403d70be33ed41d0e752a3a617ce2d175569049c9bd",
            ),
            _checkpoint(
                "selection_receipt",
                "satellite_review_runs/"
                "2026-07-21-open-seed-v83-active-explicit-"
                "new-projects-final-v1/selection-receipt.json",
                7_194,
                "ea98a8ceb3d3b457e84e1ae0db06ed28c12e39437c649c50f8c495dc3041fc45",
                binding=("manifest", "/selection_receipt"),
            ),
        ],
        limitations=[
            "Catalog availability and selected scene IDs are review controls, not visible-change, identity, lifecycle, operating-status, type, capacity, power, energy, PUE, workload, or unique-site evidence.",
            "The batch represents 104 active-priority seed-v83 queue jobs but executes only four immutable receipt IDs; 100 jobs remain pending and all counts are non-additive with the v83 queue.",
            "Three jobs preserve raw STAC scene pairs for later review; the Jashore baseline was unavailable and creates no promoted catalog directory, change result, or Atlas mutation.",
        ],
        metrics=[
            _metric("atlas_mutation", "manifest", "/scope/atlas_mutation", False),
            _metric(
                "change_analysis_executed",
                "manifest",
                "/scope/change_analysis_executed",
                False,
            ),
            _metric(
                "http_attempt_cap",
                "manifest",
                "/lifetime_budget/http_attempt_cap",
                8,
            ),
            _metric(
                "http_attempts_remaining",
                "manifest",
                "/lifetime_budget/http_attempts_remaining",
                0,
            ),
            _metric(
                "http_attempts_reserved",
                "manifest",
                "/lifetime_budget/http_attempts_reserved",
                8,
            ),
            _metric("jobs_completed", "manifest", "/summary/jobs_completed", 3),
            _metric("jobs_failed", "manifest", "/summary/jobs_failed", 0),
            _metric(
                "jobs_not_selected",
                "manifest",
                "/summary/jobs_not_selected",
                100,
            ),
            _metric("jobs_pending", "manifest", "/summary/jobs_pending", 100),
            _metric(
                "jobs_represented",
                "manifest",
                "/summary/jobs_represented",
                104,
            ),
            _metric(
                "jobs_selected_for_execution",
                "manifest",
                "/summary/jobs_selected_for_execution",
                4,
            ),
            _metric(
                "jobs_unavailable_no_scene",
                "manifest",
                "/summary/jobs_unavailable_no_scene",
                1,
            ),
            _metric(
                "review_required", "manifest", "/scope/review_required", True
            ),
            _metric(
                "unexpected_output_adoption",
                "manifest",
                "/scope/unexpected_output_adoption",
                False,
            ),
        ],
        record_units=["catalog_job", "catalog_link"],
    )
    analyst_review = _review_entry(
        artifact_id=(
            "satellite-change-review-open-seed-v83-active-explicit-"
            "new-projects-3-review-v2"
        ),
        artifact_kind="analyst_imagery_review",
        checkpoints=[
            _checkpoint(
                "blind_decisions",
                "satellite_change_reviews/"
                "2026-07-21-open-seed-v83-active-explicit-"
                "new-projects-3-review-v2/blind-decisions.json",
                4_646,
                "99dfa722aa3d6bd914d450dda528ccec5e7670eeb66157a85880d1356eb3c06a",
                binding=("manifest", "/artifacts/blind-decisions.json"),
            ),
            _checkpoint(
                "definition",
                "satellite_change_reviews/"
                "2026-07-21-open-seed-v83-active-explicit-"
                "new-projects-3-review-v2/definition.json",
                6_622,
                "9328509714323a523b4adb8dd3a1131ae960c120f56a6beaf9ffb64d35f288c3",
                binding=("manifest", "/artifacts/definition.json"),
            ),
            _checkpoint(
                "manifest",
                "satellite_change_reviews/"
                "2026-07-21-open-seed-v83-active-explicit-"
                "new-projects-3-review-v2/manifest.json",
                6_526,
                "4cbe507b44e830a92879079cc9f33290d9d64459e1b1a33a9d2944737e3eba33",
            ),
            _checkpoint(
                "summary",
                "satellite_change_reviews/"
                "2026-07-21-open-seed-v83-active-explicit-"
                "new-projects-3-review-v2/summary.json",
                5_477,
                "7ff6f4ff7499892cfc9c38278b85a868fb264f5c6379277205d11a4ca0fd47e3",
                binding=("manifest", "/artifacts/summary.json"),
            ),
        ],
        limitations=[
            "The 12 inspected visuals, 15 hash-bound review inputs, and 35 machine proposal features are non-additive review records and create no Atlas mutation, automated promotion, identity, location, project, lifecycle, operating-status, type, capacity, power, energy, PUE, operator, workload, or site-count claim.",
            "The three identity-blind decisions classify one pair as ambiguous and uncertain for manual follow-up and reject two for site promotion; no disposition establishes or negates construction, lifecycle, operating status, or any separately sourced fact.",
            "The unavailable Jashore catalog job has no analyst decision; the post-run assertion and premature-publication controls are technical incidents, not model or analyst outcomes.",
        ],
        metrics=[
            _metric(
                "analyst_decisions", "manifest", "/summary/analyst_decisions", 3
            ),
            _metric("atlas_mutation", "manifest", "/guardrails/atlas_mutation", False),
            _metric(
                "automated_promotion_allowed",
                "manifest",
                "/guardrails/automated_promotion_allowed",
                False,
            ),
            _metric(
                "capacity_claim_created",
                "manifest",
                "/guardrails/capacity_claim_created",
                False,
            ),
            _metric(
                "construction_status_claim_created",
                "manifest",
                "/guardrails/construction_status_claim_created",
                False,
            ),
            _metric(
                "current_status_claim_created",
                "manifest",
                "/guardrails/current_status_claim_created",
                False,
            ),
            _metric(
                "data_centre_identity_claim_created",
                "manifest",
                "/guardrails/data_centre_identity_claim_created",
                False,
            ),
            _metric(
                "data_centre_type_claim_created",
                "manifest",
                "/guardrails/data_centre_type_claim_created",
                False,
            ),
            _metric(
                "energy_claim_created",
                "manifest",
                "/guardrails/energy_claim_created",
                False,
            ),
            _metric(
                "image_quality_partially_obscured",
                "manifest",
                "/summary/image_quality/partially_obscured",
                2,
            ),
            _metric(
                "image_quality_unusable",
                "manifest",
                "/summary/image_quality/unusable",
                0,
            ),
            _metric(
                "image_quality_usable",
                "manifest",
                "/summary/image_quality/usable",
                1,
            ),
            _metric(
                "imagery_construction_truth_claim_created",
                "manifest",
                "/guardrails/imagery_construction_truth_claim_created",
                False,
            ),
            _metric(
                "it_capacity_claim_created",
                "manifest",
                "/guardrails/it_capacity_claim_created",
                False,
            ),
            _metric(
                "lifecycle_status_claim_created",
                "manifest",
                "/guardrails/lifecycle_status_claim_created",
                False,
            ),
            _metric(
                "location_claim_created",
                "manifest",
                "/guardrails/location_claim_created",
                False,
            ),
            _metric(
                "machine_proposal_features_reviewed",
                "manifest",
                "/summary/machine_proposal_features_reviewed",
                35,
            ),
            _metric(
                "machine_run_failures",
                "manifest",
                "/summary/machine_run_failures",
                0,
            ),
            _metric(
                "machine_run_jobs_completed_once",
                "manifest",
                "/summary/machine_run_jobs_completed_once",
                3,
            ),
            _metric(
                "machine_run_retries",
                "manifest",
                "/summary/machine_run_retries",
                0,
            ),
            _metric(
                "operator_claim_created",
                "manifest",
                "/guardrails/operator_claim_created",
                False,
            ),
            _metric(
                "power_claim_created",
                "manifest",
                "/guardrails/power_claim_created",
                False,
            ),
            _metric(
                "project_claim_created",
                "manifest",
                "/guardrails/project_claim_created",
                False,
            ),
            _metric(
                "promotion_rejected",
                "manifest",
                "/summary/promotion_dispositions/rejected_for_site_promotion",
                2,
            ),
            _metric(
                "promotion_retained_for_manual_followup",
                "manifest",
                "/summary/promotion_dispositions/retained_for_manual_followup",
                0,
            ),
            _metric(
                "promotion_uncertain_for_manual_followup",
                "manifest",
                "/summary/promotion_dispositions/uncertain_for_manual_followup",
                1,
            ),
            _metric(
                "pue_claim_created",
                "manifest",
                "/guardrails/pue_claim_created",
                False,
            ),
            _metric(
                "review_input_artifacts_hash_bound",
                "manifest",
                "/summary/review_input_artifacts_hash_bound",
                15,
            ),
            _metric(
                "site_count_claim_created",
                "manifest",
                "/guardrails/site_count_claim_created",
                False,
            ),
            _metric(
                "technical_incidents_without_model_or_analyst_outcome",
                "manifest",
                "/summary/technical_incidents_without_model_or_analyst_outcome",
                1,
            ),
            _metric(
                "unavailable_catalog_jobs_without_analyst_decision",
                "manifest",
                "/summary/unavailable_catalog_jobs_without_analyst_decision",
                1,
            ),
            _metric(
                "unique_site_claim_created",
                "manifest",
                "/guardrails/unique_site_claim_created",
                False,
            ),
            _metric(
                "visible_change_ambiguous",
                "manifest",
                "/summary/visible_change/ambiguous",
                1,
            ),
            _metric(
                "visible_change_clear",
                "manifest",
                "/summary/visible_change/clear",
                1,
            ),
            _metric(
                "visible_change_none",
                "manifest",
                "/summary/visible_change/none",
                1,
            ),
            _metric(
                "visual_artifacts_inspected",
                "manifest",
                "/summary/visual_artifacts_inspected",
                12,
            ),
            _metric(
                "workload_claim_created",
                "manifest",
                "/guardrails/workload_claim_created",
                False,
            ),
        ],
        record_units=["aggregate_report_metric", "review_record"],
    )
    candidates = {
        analyst_review["artifact_id"]: analyst_review,
        catalog["artifact_id"]: catalog,
    }
    return {
        artifact_id: candidates[artifact_id]
        for artifact_id in sorted(ADDED_ARTIFACT_IDS)
    }


def _historical_entries(
    base_entries: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for artifact_id in sorted(HISTORICAL_ARTIFACT_IDS):
        entry = deepcopy(dict(base_entries[artifact_id]))
        entry["current_role"] = "public_supporting_review_lane"
        entry["limitations"] = sorted(
            [
                *entry["limitations"],
                "This accepted seed-v71 review artifact is historical and must not be represented as seed-v83 satellite coverage.",
            ]
        )
        result[artifact_id] = entry
    return result


def pending_downstream_pins() -> tuple[str, ...]:
    return tuple(
        sorted(
            artifact_id
            for artifact_id, spec in PENDING_DOWNSTREAM_REPLACEMENTS.items()
            if spec is None
        )
    )


def _require_downstream_pins() -> None:
    pending = pending_downstream_pins()
    if pending:
        raise PendingDownstreamPinsError(
            "v24 downstream pins remain unresolved: " + ", ".join(pending)
        )


def _validate_accepted_inputs(package_root: str | Path) -> dict[str, dict[str, Any]]:
    root = Path(package_root).resolve()
    base_definition, _base_ledger = _load_v23_base(root)
    for label, (relative, byte_count, digest, mode) in _ACCEPTED_FILES.items():
        path = _inside(root, relative, f"accepted {label}")
        if path.is_symlink() or not path.is_file():
            raise CurrentCoverageV24Error(f"accepted {label} is not a regular file")
        raw = path.read_bytes()
        if (
            len(raw) != byte_count
            or _sha256(raw) != digest
            or stat.S_IMODE(path.stat().st_mode) != mode
        ):
            raise CurrentCoverageV24Error(f"accepted {label} pin or mode changed")
    for artifact_id, decision in NON_LEDGER_ARTIFACT_DECISIONS.items():
        checkpoint = decision["manifest"]
        path = _inside(
            root,
            str(checkpoint["path"]),
            f"non-ledger {artifact_id} manifest",
        )
        if path.is_symlink() or not path.is_file():
            raise CurrentCoverageV24Error(
                f"non-ledger {artifact_id} manifest is not regular"
            )
        raw = path.read_bytes()
        if (
            len(raw) != checkpoint["bytes"]
            or _sha256(raw) != checkpoint["sha256"]
            or stat.S_IMODE(path.stat().st_mode) != 0o444
        ):
            raise CurrentCoverageV24Error(
                f"non-ledger {artifact_id} manifest pin changed"
            )
        tree = decision.get("tree")
        if tree is not None:
            tree_path = _inside(
                root,
                str(tree["path"]),
                f"non-ledger {artifact_id} tree",
            )
            if (
                _tree_digest(tree_path) != tree["sha256"]
                or stat.S_IMODE(tree_path.stat().st_mode) != 0o555
            ):
                raise CurrentCoverageV24Error(
                    f"non-ledger {artifact_id} tree changed"
                )
    for label, (relative, digest) in _ACCEPTED_TREES.items():
        path = _inside(root, relative, f"accepted {label} tree")
        if _tree_digest(path) != digest:
            raise CurrentCoverageV24Error(f"accepted {label} tree changed")
        if stat.S_IMODE(path.stat().st_mode) != 0o555:
            raise CurrentCoverageV24Error(f"accepted {label} tree is not frozen")
    now = datetime.now(UTC)
    for label, (relative, field, expected) in _SOURCE_TIMESTAMPS.items():
        path = _inside(root, relative, f"accepted {label} timestamp")
        _, document = _read_json(path, f"accepted {label} timestamp")
        if document.get(field) != expected:
            raise CurrentCoverageV24Error(f"accepted {label} timestamp changed")
        if _parse_pinned_source_timestamp(expected, label) > now:
            raise CurrentCoverageV24Error(f"accepted {label} timestamp is future")
    for label, (relative, expected) in _ACCEPTED_ROOT_NOT_BEFORE.items():
        path = _inside(root, relative, f"accepted {label} root")
        target = _parse_timestamp(expected, f"accepted {label} publication")
        if path.stat(follow_symlinks=False).st_ctime + 1e-6 < target.timestamp():
            raise CurrentCoverageV24Error(
                f"accepted {label} root predates its publication time"
            )
    base_entries = {
        entry["artifact_id"]: entry for entry in base_definition["entries"]
    }
    accepted = _accepted_replacement_entries(base_entries)
    accepted.update(_accepted_addition_entries())
    if set(accepted) != NEW_ARTIFACT_IDS:
        raise CurrentCoverageV24Error("v24 accepted artifact inventory changed")
    previous_id: str | None = None
    for artifact_id in sorted(accepted):
        try:
            artifact = _v22._v21._entry_v4(
                root, accepted[artifact_id], previous_id
            )
        except _v22._v21.CurrentCoverageV21Error as error:
            raise CurrentCoverageV24Error(str(error)) from error
        previous_id = artifact["artifact_id"]
    return accepted


_UPDATED_GAP_SUMMARIES = {
    "benchmark-parity-not-computed": (
        "No licensed, row-level external benchmark denominator is pinned; the 43 selected calibration labels, three current seed-v83 identity-blind analyst decisions, 11 historical seed-v71 identity-blind dispositions, and 506 source-scoped last-observed timelines provide neither recall nor SemiAnalysis-equivalent precision, feature, field, current-status, or quarterly parity."
    ),
    "global-construction-coverage-partial": (
        "The expanded official open seed, planning and permit review lanes, structural shortlist, footprint context, 506 last-observed timelines, and current seed-v83 satellite catalog and analyst-review controls still do not establish a complete global construction census; queue, catalog, and analyst-review controls are non-additive and promote no site or lifecycle claim."
    ),
    "satellite-review-backlog": (
        "Unknown034 remains the accepted cumulative unknown-priority catalog checkpoint with 4,397 completed, 303 no-scene, 2,036 pending, and zero failed. Separately, the current seed-v83 queue has 200 review jobs, including 104 last-observed active-construction priorities, while 705 seed rows lack coordinates. The current v83 catalog represents 104 jobs, selects four, completes three, records one unavailable scene pair, and leaves 100 pending. Three v83 analyst decisions retain one uncertain pair for manual follow-up and reject two for site promotion; none promotes a site or status claim. The accepted seed-v71 catalog and 11 analyst dispositions remain historical and are not v83 coverage. All counts are non-additive and manual verification remains open."
    ),
    "site-resolution-partial": (
        "Resolution links remain advisory; England, Ireland, NSW, Netherlands, New Zealand, and France observations, 506 source-scoped lifecycle timelines, and current or historical selected imagery labels are not cross-source deduplicated, no merges are accepted, and unique physical sites remain null."
    ),
}


def preview_parity_gaps(package_root: str | Path) -> list[dict[str, Any]]:
    base_definition, _ = _load_v23_base(Path(package_root).resolve())
    result: list[dict[str, Any]] = []
    for raw_gap in base_definition["parity_gaps"]:
        gap = deepcopy(raw_gap)
        gap["affected_artifact_ids"] = sorted(
            {
                ARTIFACT_REPLACEMENTS.get(artifact_id, artifact_id)
                for artifact_id in gap["affected_artifact_ids"]
            }
        )
        if gap["gap_id"] in {
            "global-construction-coverage-partial",
            "satellite-review-backlog",
        }:
            gap["affected_artifact_ids"] = sorted(
                {*gap["affected_artifact_ids"], *ADDED_ARTIFACT_IDS}
            )
        if gap["gap_id"] in _UPDATED_GAP_SUMMARIES:
            gap["summary"] = _UPDATED_GAP_SUMMARIES[gap["gap_id"]]
        result.append(gap)
    return result


def preview_v24_delta(package_root: str | Path) -> dict[str, Any]:
    root = Path(package_root).resolve()
    base_definition, _ = _load_v23_base(root)
    accepted = _validate_accepted_inputs(root)
    base_entries = {
        entry["artifact_id"]: entry for entry in base_definition["entries"]
    }
    unchanged = [
        base_entries[artifact_id]
        for artifact_id in sorted(
            set(base_entries) - REMOVED_ARTIFACT_IDS - HISTORICAL_ARTIFACT_IDS
        )
    ]
    historical = list(_historical_entries(base_entries).values())
    removed = [
        base_entries[artifact_id] for artifact_id in sorted(REMOVED_ARTIFACT_IDS)
    ]
    replacements = [
        accepted[artifact_id]
        for artifact_id in sorted(REPLACEMENT_ARTIFACT_IDS)
    ]
    additions = [
        accepted[artifact_id] for artifact_id in sorted(ADDED_ARTIFACT_IDS)
    ]
    if (
        len(unchanged) != 40
        or len(historical) != 2
        or len(removed) != 8
        or len(replacements) != 8
        or len(additions) != len(ADDED_ARTIFACT_IDS)
    ):
        raise CurrentCoverageV24Error("v24 prep delta arithmetic changed")
    if UNCHANGED_40_SHA256 is None or (
        _component_digest(unchanged) != UNCHANGED_40_SHA256
    ):
        raise CurrentCoverageV24Error("v24 unchanged-entry digest changed")
    if REMOVED_8_SHA256 is None or _component_digest(removed) != REMOVED_8_SHA256:
        raise CurrentCoverageV24Error("v24 removed-entry digest changed")
    if (
        REPLACEMENT_8_SHA256 is None
        or _component_digest(replacements) != REPLACEMENT_8_SHA256
    ):
        raise CurrentCoverageV24Error("v24 replacement-entry digest changed")
    if (
        HISTORICAL_2_SHA256 is None
        or _component_digest(historical) != HISTORICAL_2_SHA256
    ):
        raise CurrentCoverageV24Error("v24 historical-entry digest changed")
    if (
        ADDED_ARTIFACTS_SHA256 is None
        or _component_digest(additions) != ADDED_ARTIFACTS_SHA256
    ):
        raise CurrentCoverageV24Error("v24 added-entry digest changed")
    combined = {entry["artifact_id"]: entry for entry in unchanged}
    combined.update({entry["artifact_id"]: entry for entry in historical})
    combined.update(accepted)
    ordered = [combined[artifact_id] for artifact_id in sorted(combined)]
    if ALL_ENTRIES_SHA256 is None or _component_digest(ordered) != ALL_ENTRIES_SHA256:
        raise CurrentCoverageV24Error("v24 all-entry digest changed")
    if _sha256(_canonical_line(preview_parity_gaps(root))) != PARITY_GAPS_SHA256:
        raise CurrentCoverageV24Error("v24 parity-gap digest changed")
    return {
        "accepted_added_ids": sorted(ADDED_ARTIFACT_IDS),
        "historical_retained_ids": sorted(HISTORICAL_ARTIFACT_IDS),
        "accepted_replacement_ids": sorted(REPLACEMENT_ARTIFACT_IDS),
        "base_entries": len(base_entries),
        "final_entries": 50 + len(ADDED_ARTIFACT_IDS),
        "pending_replacement_ids": list(pending_downstream_pins()),
        "parity_gaps_sha256": PARITY_GAPS_SHA256,
        "removed_8_sha256": REMOVED_8_SHA256,
        "replacement_8_sha256": REPLACEMENT_8_SHA256,
        "historical_2_sha256": HISTORICAL_2_SHA256,
        "added_artifacts_sha256": ADDED_ARTIFACTS_SHA256,
        "unchanged_40_sha256": UNCHANGED_40_SHA256,
    }


def make_v24_definition(package_root: str | Path, *, generated_at: str) -> bytes:
    """Render v24 only after all eight replacements and final digests are sealed."""

    root = Path(package_root).resolve()
    base_definition, _ = _load_v23_base(root)
    accepted = _validate_accepted_inputs(root)
    _require_downstream_pins()
    if (
        REPLACEMENT_8_SHA256 is None
        or HISTORICAL_2_SHA256 is None
        or ADDED_ARTIFACTS_SHA256 is None
        or ALL_ENTRIES_SHA256 is None
        or V24_GENERATED_AT is None
    ):
        raise PendingDownstreamPinsError("v24 replacement digest fuses are unresolved")
    generated = _parse_timestamp(generated_at, "v24 generated_at")
    if generated_at != V24_GENERATED_AT:
        raise CurrentCoverageV24Error("v24 generated_at changed")
    for label, (_relative, _field, expected) in _SOURCE_TIMESTAMPS.items():
        if _parse_pinned_source_timestamp(expected, label) > generated:
            raise CurrentCoverageV24Error(
                f"accepted {label} post-dates v24 generated_at"
            )
    new_entries = dict(accepted)
    new_entries.update(
        {
            artifact_id: deepcopy(dict(spec))
            for artifact_id, spec in PENDING_DOWNSTREAM_REPLACEMENTS.items()
            if spec is not None
        }
    )
    if set(new_entries) != NEW_ARTIFACT_IDS:
        raise CurrentCoverageV24Error("v24 new artifact inventory changed")
    base_entries = {
        entry["artifact_id"]: deepcopy(entry)
        for entry in base_definition["entries"]
    }
    for artifact_id in REMOVED_ARTIFACT_IDS:
        del base_entries[artifact_id]
    base_entries.update(_historical_entries(base_entries))
    base_entries.update(new_entries)
    ordered = [base_entries[artifact_id] for artifact_id in sorted(base_entries)]
    replacement_rows = [
        base_entries[artifact_id] for artifact_id in sorted(REPLACEMENT_ARTIFACT_IDS)
    ]
    added_rows = [
        base_entries[artifact_id] for artifact_id in sorted(ADDED_ARTIFACT_IDS)
    ]
    historical_rows = [
        base_entries[artifact_id] for artifact_id in sorted(HISTORICAL_ARTIFACT_IDS)
    ]
    if (
        len(ordered) != 50 + len(ADDED_ARTIFACT_IDS)
        or _component_digest(replacement_rows) != REPLACEMENT_8_SHA256
        or _component_digest(historical_rows) != HISTORICAL_2_SHA256
        or _component_digest(added_rows) != ADDED_ARTIFACTS_SHA256
        or _component_digest(ordered) != ALL_ENTRIES_SHA256
    ):
        raise CurrentCoverageV24Error("v24 sealed entry digest changed")
    document = {
        "base_ledger": V23_BASE_LINEAGE,
        "entries": ordered,
        "generated_at": generated_at,
        "ledger_id": V24_LEDGER_ID,
        "parity_gaps": preview_parity_gaps(root),
        "schema_version": DEFINITION_SCHEMA_VERSION_V4,
        "scope": SCOPE_POLICY,
    }
    raw = _canonical_json(document)
    forbidden = {
        *REMOVED_ARTIFACT_IDS,
        "epoch-official-open-seed-v68",
        "federation-public-open-v29",
        "federation-public-open-v30",
        "federation-public-open-v32",
        "federated-index-2026-07-21-public-open-v32",
    }
    rendered = raw.decode("utf-8")
    if any(token in rendered for token in forbidden):
        raise CurrentCoverageV24Error("v24 contains superseded or rejected lineage")
    return raw


def _validate_v24_definition(
    definition_path: str | Path,
    *,
    require_live: bool,
) -> tuple[dict[str, Any], bytes, Path, datetime]:
    path = Path(definition_path).resolve()
    package_root = path.parent.parent.resolve()
    if path.parent != package_root / "sources":
        raise CurrentCoverageV24Error("v24 definition stage must be inside sources")
    raw, document = _read_json(path, "v24 definition")
    if stat.S_IMODE(path.stat().st_mode) != 0o444:
        raise CurrentCoverageV24Error("v24 definition must be frozen 0444")
    if V24_DEFINITION_SHA256 is None:
        raise PendingDownstreamPinsError("v24 definition digest fuse is unresolved")
    if _sha256(raw) != V24_DEFINITION_SHA256:
        raise CurrentCoverageV24Error("v24 definition content changed")
    generated_at = document.get("generated_at")
    if raw != make_v24_definition(package_root, generated_at=generated_at):
        raise CurrentCoverageV24Error(
            "v24 definition differs from its pinned transformation"
        )
    if set(document) != {
        "base_ledger",
        "entries",
        "generated_at",
        "ledger_id",
        "parity_gaps",
        "schema_version",
        "scope",
    }:
        raise CurrentCoverageV24Error("v24 definition keys differ")
    if (
        document.get("base_ledger") != V23_BASE_LINEAGE
        or document.get("ledger_id") != V24_LEDGER_ID
        or document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V4
        or document.get("scope") != SCOPE_POLICY
    ):
        raise CurrentCoverageV24Error("v24 identity, base, schema, or scope changed")
    generated = _parse_timestamp(generated_at, "v24 generated_at")
    if require_live and generated > datetime.now(UTC):
        raise CurrentCoverageV24Error("v24 generated_at is not yet live")
    entries = document.get("entries")
    expected_entries = 50 + len(ADDED_ARTIFACT_IDS)
    if not isinstance(entries, list) or len(entries) != expected_entries:
        raise CurrentCoverageV24Error(
            f"v24 must contain exactly {expected_entries} entries"
        )
    artifact_ids = {entry.get("artifact_id") for entry in entries}
    if (
        len(artifact_ids) != expected_entries
        or None in artifact_ids
        or artifact_ids & REMOVED_ARTIFACT_IDS
        or not NEW_ARTIFACT_IDS <= artifact_ids
    ):
        raise CurrentCoverageV24Error("v24 entry inventory is invalid")
    return document, raw, package_root, generated


def build_current_coverage_ledger_v24(
    definition_path: str | Path,
) -> CurrentCoverageV24Bundle:
    """Reproduce all three v24 bundle files without publishing any path."""

    definition, definition_raw, package_root, _generated = _validate_v24_definition(
        definition_path, require_live=False
    )
    _base_definition, base_ledger = _load_v23_base(package_root)
    artifacts: list[dict[str, Any]] = []
    previous_id: str | None = None
    for spec in definition["entries"]:
        try:
            artifact = _v22._v21._entry_v4(package_root, spec, previous_id)
        except _v22._v21.CurrentCoverageV21Error as error:
            raise CurrentCoverageV24Error(str(error)) from error
        artifacts.append(artifact)
        previous_id = artifact["artifact_id"]
    try:
        parity_gaps = _v22._v21._legacy._parity_gaps(
            definition["parity_gaps"],
            {artifact["artifact_id"] for artifact in artifacts},
        )
    except _v22._v21._legacy.CurrentCoverageError as error:
        raise CurrentCoverageV24Error(str(error)) from error
    inventory_counts = _v22._v21._inventory_counts(artifacts, parity_gaps)
    expected_inventory = deepcopy(base_ledger["artifact_inventory_counts"])
    definition_by_id = {
        entry["artifact_id"]: entry for entry in definition["entries"]
    }
    for artifact_id in sorted(ADDED_ARTIFACT_IDS):
        addition = definition_by_id[artifact_id]
        expected_inventory["artifacts"] += 1
        expected_inventory["by_access_tier"][addition["access_tier"]] += 1
        expected_inventory["by_evidence_scope"][addition["evidence_scope"]] += 1
        expected_inventory["by_publication_mode"][
            addition["publication_mode"]
        ] += 1
        for record_unit in addition["record_units"]:
            expected_inventory["by_record_unit"][record_unit] += 1
        expected_inventory["by_redistribution_status"][
            addition["redistribution_status"]
        ] += 1
        if (
            addition["access_tier"] == "public_open"
            and addition["evidence_scope"] == "review_only"
        ):
            expected_inventory["public_open_review_only_artifacts"] += 1
    if inventory_counts != expected_inventory:
        raise CurrentCoverageV24Error("v24 artifact inventory arithmetic changed")
    generated_at = definition["generated_at"]
    ledger = {
        "artifact_inventory_counts": inventory_counts,
        "artifacts": artifacts,
        "base_ledger": V23_BASE_LINEAGE,
        "format": LEDGER_FORMAT_V4,
        "generated_at": generated_at,
        "ledger_id": V24_LEDGER_ID,
        "parity_gaps": parity_gaps,
        "schema_version": LEDGER_SCHEMA_VERSION_V4,
        "scope": SCOPE_POLICY,
    }
    ledger_bytes = _canonical_json(ledger)
    manifest = {
        "artifacts": {
            LEDGER_FILENAME: {
                "bytes": len(ledger_bytes),
                "sha256": _sha256(ledger_bytes),
            }
        },
        "base_ledger": V23_BASE_LINEAGE,
        "definition": {
            "bytes": len(definition_raw),
            "path": V24_DEFINITION_PATH,
            "sha256": _sha256(definition_raw),
        },
        "format": BUNDLE_FORMAT_V4,
        "generated_at": generated_at,
        "input_checkpoints": {
            artifact["artifact_id"]: {
                checkpoint["checkpoint_id"]: {
                    "bytes": checkpoint["bytes"],
                    "path": checkpoint["path"],
                    "sha256": checkpoint["sha256"],
                }
                for checkpoint in artifact["checkpoints"]
            }
            for artifact in artifacts
        },
        "ledger_id": V24_LEDGER_ID,
        "schema_version": LEDGER_SCHEMA_VERSION_V4,
        "scope": SCOPE_POLICY,
    }
    manifest_bytes = _canonical_json(manifest)
    manifest_hash_bytes = (
        f"{_sha256(manifest_bytes)}  {MANIFEST_FILENAME}\n".encode("ascii")
    )
    return CurrentCoverageV24Bundle(
        ledger_bytes=ledger_bytes,
        manifest_bytes=manifest_bytes,
        manifest_hash_bytes=manifest_hash_bytes,
        ledger=ledger,
        manifest=manifest,
    )


def _validate_v24_bundle(
    output_path: str | Path,
    *,
    definition_path: str | Path,
    require_live: bool,
) -> dict[str, Any]:
    _require_downstream_pins()
    directory = Path(os.path.abspath(os.fspath(output_path)))
    if directory.is_symlink() or not directory.is_dir():
        raise CurrentCoverageV24Error("v24 bundle must be a regular directory")
    entries = list(directory.iterdir())
    if {entry.name for entry in entries} != BUNDLE_FILES or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV24Error("v24 bundle file set differs")
    if stat.S_IMODE(directory.stat().st_mode) != 0o555 or any(
        stat.S_IMODE(entry.stat().st_mode) != 0o444 for entry in entries
    ):
        raise CurrentCoverageV24Error("v24 bundle must be frozen 0555/0444")
    definition, _definition_raw, _root, generated = _validate_v24_definition(
        definition_path, require_live=require_live
    )
    expected = build_current_coverage_ledger_v24(definition_path)
    expected_files = {
        LEDGER_FILENAME: expected.ledger_bytes,
        MANIFEST_FILENAME: expected.manifest_bytes,
        MANIFEST_HASH_FILENAME: expected.manifest_hash_bytes,
    }
    for filename, expected_raw in expected_files.items():
        path = directory / filename
        if path.read_bytes() != expected_raw:
            raise CurrentCoverageV24Error(f"v24 {filename} differs")
    if require_live:
        _assert_final_root_ctimes(
            (Path(definition_path), directory), generated
        )
    if definition["generated_at"] != expected.manifest["generated_at"]:
        raise CurrentCoverageV24Error("v24 definition and bundle time differ")
    return dict(expected.manifest)


def _aware_utc(value: datetime | None, label: str) -> datetime:
    result = value or datetime.now(UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise CurrentCoverageV24Error(f"{label} lacks timezone")
    return result.astimezone(UTC)


def _stage_paths(definition_stage: Path, bundle_stage: Path) -> tuple[Path, ...]:
    if definition_stage.is_symlink() or not definition_stage.is_file():
        raise CurrentCoverageV24Error("v24 definition stage must be a regular file")
    if bundle_stage.is_symlink() or not bundle_stage.is_dir():
        raise CurrentCoverageV24Error("v24 bundle stage must be a regular directory")
    descendants = sorted(
        bundle_stage.rglob("*"), key=lambda path: path.relative_to(bundle_stage).as_posix()
    )
    for path in descendants:
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise CurrentCoverageV24Error(f"v24 stage is contaminated: {path}")
    return (definition_stage, bundle_stage, *descendants)


def _assert_stage_precedes_target(
    paths: Sequence[Path], generated_at: datetime
) -> None:
    target = generated_at.timestamp()
    for path in paths:
        metadata = path.stat(follow_symlinks=False)
        if not hasattr(metadata, "st_birthtime"):
            raise CurrentCoverageV24Error("filesystem birth time is unavailable")
        if max(metadata.st_birthtime, metadata.st_mtime) > target + 0.000_001:
            raise CurrentCoverageV24Error(
                f"v24 private stage post-dates generated_at: {path.name}"
            )


def _assert_final_root_ctimes(
    final_paths: Sequence[Path], generated_at: datetime
) -> None:
    target = generated_at.timestamp()
    for path in final_paths:
        if path.is_symlink() or not path.exists():
            raise CurrentCoverageV24Error(f"v24 final root is absent: {path}")
        if path.stat(follow_symlinks=False).st_ctime + 0.000_001 < target:
            raise CurrentCoverageV24Error(
                f"v24 final root rename predates generated_at: {path.name}"
            )


def validate_private_staging_boundary(
    staged_definition: str | Path,
    staged_bundle: str | Path,
    final_definition: str | Path,
    final_bundle: str | Path,
    *,
    wall_clock: datetime | None = None,
) -> datetime:
    """Allow hidden future-dated stages only when every staged inode precedes it."""

    definition_stage = Path(staged_definition)
    bundle_stage = Path(staged_bundle)
    _raw, document = _read_json(definition_stage, "staged v24 definition")
    if document.get("ledger_id") != V24_LEDGER_ID:
        raise CurrentCoverageV24Error("staged v24 ledger identity changed")
    if document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V4:
        raise CurrentCoverageV24Error("staged v24 schema changed")
    generated = _parse_timestamp(document.get("generated_at"), "v24 generated_at")
    now = _aware_utc(wall_clock, "v24 staging wall clock")
    if now >= generated:
        raise CurrentCoverageV24Error(
            "v24 generated_at must remain future while private staging completes"
        )
    for final in (Path(final_definition), Path(final_bundle)):
        if final.exists() or final.is_symlink():
            raise CurrentCoverageV24Error("v24 final path exposed during staging")
    _assert_stage_precedes_target(
        _stage_paths(definition_stage, bundle_stage), generated
    )
    return generated


def validate_prepublication_boundary(
    staged_definition: str | Path,
    final_definition: str | Path,
    final_bundle: str | Path,
    *,
    staged_bundle: str | Path | None = None,
    wall_clock: datetime | None = None,
) -> datetime:
    """Reject early exposure, a non-live target, or post-target staged bytes."""

    stage = Path(staged_definition)
    raw, document = _read_json(stage, "staged v24 definition")
    if document.get("ledger_id") != V24_LEDGER_ID:
        raise CurrentCoverageV24Error("staged v24 ledger identity changed")
    if document.get("schema_version") != DEFINITION_SCHEMA_VERSION_V4:
        raise CurrentCoverageV24Error("staged v24 schema changed")
    generated = _parse_timestamp(document.get("generated_at"), "v24 generated_at")
    now = _aware_utc(wall_clock, "v24 publication wall clock")
    final_definition_path = Path(final_definition)
    final_bundle_path = Path(final_bundle)
    definition_exposed = (
        final_definition_path.exists() or final_definition_path.is_symlink()
    )
    bundle_exposed = final_bundle_path.exists() or final_bundle_path.is_symlink()
    if now < generated and definition_exposed:
        raise CurrentCoverageV24Error(
            "final v24 definition was exposed before generated_at"
        )
    if now < generated and bundle_exposed:
        raise CurrentCoverageV24Error(
            "final v24 bundle was exposed before generated_at"
        )
    if definition_exposed or bundle_exposed:
        raise CurrentCoverageV24Error("v24 final path collision")
    if now < generated:
        raise CurrentCoverageV24Error("v24 generated_at is not yet live")
    if V24_DEFINITION_SHA256 is None:
        raise PendingDownstreamPinsError("v24 definition digest fuse is unresolved")
    if _sha256(raw) != V24_DEFINITION_SHA256:
        raise CurrentCoverageV24Error("staged v24 definition digest changed")
    if staged_bundle is not None:
        bundle_stage = Path(staged_bundle)
        _validate_v24_bundle(
            bundle_stage, definition_path=stage, require_live=False
        )
        paths = _stage_paths(stage, bundle_stage)
    else:
        paths = (stage,)
    _assert_stage_precedes_target(paths, generated)
    return generated


def preflight_v24_publication(package_root: str | Path) -> dict[str, Any]:
    """Validate accepted inputs and report the unresolved publication fuses."""

    root = Path(package_root).resolve()
    preview = preview_v24_delta(root)
    final_definition = root / V24_DEFINITION_PATH
    final_bundle = root / V24_BUNDLE_PATH
    if final_definition.exists() or final_definition.is_symlink():
        raise CurrentCoverageV24Error("v24 final definition must remain absent")
    if final_bundle.exists() or final_bundle.is_symlink():
        raise CurrentCoverageV24Error("v24 final bundle must remain absent")
    _require_downstream_pins()
    if V24_DEFINITION_SHA256 is None:
        raise PendingDownstreamPinsError("v24 definition digest fuse is unresolved")
    return preview


def _fsync_regular(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _path_identity(path: Path, *, directory: bool) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    expected = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(
        metadata.st_mode
    )
    if not expected:
        raise CurrentCoverageV24Error(f"v24 stage type changed: {path}")
    return metadata.st_dev, metadata.st_ino


def _discard_file_stage(path: Path, identity: tuple[int, int]) -> None:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISREG(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != identity
    ):
        raise CurrentCoverageV24Error("refusing substituted v24 definition stage")
    path.chmod(0o600)
    path.unlink()


def _discard_bundle_stage(
    path: Path,
    identity: tuple[int, int],
    member_identities: Mapping[str, tuple[int, int]] | None = None,
) -> None:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != identity
    ):
        raise CurrentCoverageV24Error("refusing substituted v24 bundle stage")
    entries = list(path.iterdir())
    if not {entry.name for entry in entries}.issubset(BUNDLE_FILES) or any(
        entry.is_symlink() or not entry.is_file() for entry in entries
    ):
        raise CurrentCoverageV24Error("refusing contaminated v24 bundle cleanup")
    if member_identities is not None:
        actual = {
            entry.name: (
                entry.stat(follow_symlinks=False).st_dev,
                entry.stat(follow_symlinks=False).st_ino,
            )
            for entry in entries
        }
        if actual != dict(member_identities):
            raise CurrentCoverageV24Error(
                "refusing identity-changed v24 bundle cleanup"
            )
    path.chmod(0o700)
    for entry in entries:
        entry.chmod(0o600)
        entry.unlink()
    path.rmdir()


@contextmanager
def _publication_locks(
    final_definition: Path, final_bundle: Path
) -> Iterator[None]:
    try:
        with _v22._v21._exclusive_output_lock(final_definition):
            with _v22._v21._exclusive_output_lock(final_bundle):
                yield
    except _v22._v21.CurrentCoverageV21Error as error:
        raise CurrentCoverageV24Error(str(error).replace("v22", "v24")) from error


def _require_final_paths_absent(
    final_definition: Path, final_bundle: Path, label: str
) -> None:
    if final_definition.exists() or final_definition.is_symlink():
        raise CurrentCoverageV24Error(f"{label} v24 definition path is occupied")
    if final_bundle.exists() or final_bundle.is_symlink():
        raise CurrentCoverageV24Error(f"{label} v24 bundle path is occupied")


def _prepare_v24_publication(
    package_root: Path,
    *,
    generated_at: str,
    wall_clock: datetime,
) -> _PreparedV24Publication:
    final_definition = package_root / V24_DEFINITION_PATH
    final_bundle = package_root / V24_BUNDLE_PATH
    raw = make_v24_definition(package_root, generated_at=generated_at)
    if V24_DEFINITION_SHA256 is None or _sha256(raw) != V24_DEFINITION_SHA256:
        raise CurrentCoverageV24Error("v24 staged definition digest changed")

    definition_stage: Path | None = None
    bundle_stage: Path | None = None
    definition_identity: tuple[int, int] | None = None
    bundle_identity: tuple[int, int] | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{final_definition.name}.",
            suffix=".stage",
            dir=final_definition.parent,
        )
        definition_stage = Path(temporary)
        definition_identity = _path_identity(definition_stage, directory=False)
        with os.fdopen(descriptor, "wb") as destination:
            destination.write(raw)
            destination.flush()
            os.fsync(destination.fileno())
        definition_stage.chmod(0o444)
        _fsync_regular(definition_stage)

        bundle_stage = Path(
            tempfile.mkdtemp(
                prefix=f".{final_bundle.name}.", dir=final_bundle.parent
            )
        )
        bundle_identity = _path_identity(bundle_stage, directory=True)
        bundle = build_current_coverage_ledger_v24(definition_stage)
        staged_files = {
            LEDGER_FILENAME: bundle.ledger_bytes,
            MANIFEST_FILENAME: bundle.manifest_bytes,
            MANIFEST_HASH_FILENAME: bundle.manifest_hash_bytes,
        }
        for filename, content in staged_files.items():
            path = bundle_stage / filename
            _v22._v21._write_file(path, content)
            path.chmod(0o444)
            _fsync_regular(path)
        bundle_stage.chmod(0o555)
        _fsync_directory(bundle_stage)
        _validate_v24_bundle(
            bundle_stage, definition_path=definition_stage, require_live=False
        )
        generated = validate_private_staging_boundary(
            definition_stage,
            bundle_stage,
            final_definition,
            final_bundle,
            wall_clock=wall_clock,
        )
        return _PreparedV24Publication(
            bundle_identity=bundle_identity,
            bundle_member_identities={
                path.name: _path_identity(path, directory=False)
                for path in bundle_stage.iterdir()
            },
            bundle_stage=bundle_stage,
            bundle_tree_sha256=_tree_digest(bundle_stage),
            definition_identity=definition_identity,
            definition_raw=raw,
            definition_stage=definition_stage,
            generated_at=generated,
        )
    except BaseException as primary_error:
        try:
            if bundle_stage is not None and bundle_identity is not None:
                _discard_bundle_stage(bundle_stage, bundle_identity)
            if definition_stage is not None and definition_identity is not None:
                _discard_file_stage(definition_stage, definition_identity)
        except Exception as cleanup_error:
            primary_error.add_note(f"v24 stage cleanup failed: {cleanup_error}")
        raise


def _wait_until(
    target: float,
    *,
    clock: Callable[[], float],
    sleeper: Callable[[float], None],
) -> None:
    while True:
        remaining = target - clock()
        if remaining <= 0:
            return
        sleeper(min(remaining, 0.25))


def _path_has_identity(path: Path, identity: tuple[int, int], *, directory: bool) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    expected_type = (
        stat.S_ISDIR(metadata.st_mode)
        if directory
        else stat.S_ISREG(metadata.st_mode)
    )
    return expected_type and (metadata.st_dev, metadata.st_ino) == identity


def _rollback_owned_bundle_promotion(
    prepared: _PreparedV24Publication, final_bundle: Path
) -> None:
    if not _path_has_identity(
        final_bundle, prepared.bundle_identity, directory=True
    ):
        raise CurrentCoverageV24Error(
            "refusing rollback of a substituted v24 final bundle"
        )
    if prepared.bundle_stage.exists() or prepared.bundle_stage.is_symlink():
        raise CurrentCoverageV24Error(
            "refusing rollback over an occupied v24 private bundle stage"
        )
    try:
        _v22._v21._promote_noreplace(final_bundle, prepared.bundle_stage)
    except _v22._v21.CurrentCoverageV21Error as error:
        raise CurrentCoverageV24Error(
            str(error).replace("v22", "v24")
        ) from error
    if final_bundle.exists() or final_bundle.is_symlink() or not _path_has_identity(
        prepared.bundle_stage, prepared.bundle_identity, directory=True
    ):
        raise CurrentCoverageV24Error(
            "v24 bundle rollback did not restore the owned private inode"
        )
    prepared.bundle_stage.chmod(0o555)
    _fsync_directory(prepared.bundle_stage)
    _fsync_directory(final_bundle.parent)


def _promote_staged_pair(
    prepared: _PreparedV24Publication,
    final_definition: Path,
    final_bundle: Path,
) -> None:
    if stat.S_IMODE(prepared.bundle_stage.stat().st_mode) != 0o555:
        raise CurrentCoverageV24Error(
            "v24 private bundle must be frozen before its promotion transition"
        )
    prepared.bundle_stage.chmod(0o755)
    _fsync_directory(prepared.bundle_stage)
    try:
        _v22._v21._promote_noreplace(prepared.bundle_stage, final_bundle)
    except _v22._v21.CurrentCoverageV21Error as error:
        if _path_has_identity(
            prepared.bundle_stage, prepared.bundle_identity, directory=True
        ):
            prepared.bundle_stage.chmod(0o555)
            _fsync_directory(prepared.bundle_stage)
        raise CurrentCoverageV24Error(
            str(error).replace("v22", "v24")
        ) from error
    if not _path_has_identity(final_bundle, prepared.bundle_identity, directory=True):
        raise CurrentCoverageV24Error("v24 final bundle identity changed on promotion")
    _fsync_directory(final_bundle.parent)
    try:
        _v22._v21._promote_noreplace(prepared.definition_stage, final_definition)
    except BaseException as definition_error:
        try:
            _rollback_owned_bundle_promotion(prepared, final_bundle)
        except Exception as rollback_error:
            definition_error.add_note(
                f"v24 owned-bundle rollback failed: {rollback_error}"
            )
        if isinstance(definition_error, _v22._v21.CurrentCoverageV21Error):
            raise CurrentCoverageV24Error(
                str(definition_error).replace("v22", "v24")
            ) from definition_error
        raise
    if not _path_has_identity(
        final_definition, prepared.definition_identity, directory=False
    ):
        raise CurrentCoverageV24Error(
            "v24 final definition identity changed on promotion"
        )
    final_bundle.chmod(0o555)
    _fsync_directory(final_bundle)
    _fsync_directory(final_definition.parent)


def publish_current_coverage_v24(
    package_root: str | Path,
    *,
    generated_at: str,
    _clock: Callable[[], float] = time.time,
    _sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Stage both artifacts before target, then publish them without replacement."""

    root = Path(package_root).resolve()
    final_definition = root / V24_DEFINITION_PATH
    final_bundle = root / V24_BUNDLE_PATH
    target = _parse_timestamp(generated_at, "v24 generated_at")
    if _clock() >= target.timestamp():
        raise CurrentCoverageV24Error(
            "v24 generated_at must be future before private staging starts"
        )
    preflight_v24_publication(root)
    with _publication_locks(final_definition, final_bundle):
        _require_final_paths_absent(final_definition, final_bundle, "initial")
        prepared = _prepare_v24_publication(
            root,
            generated_at=generated_at,
            wall_clock=datetime.fromtimestamp(_clock(), UTC),
        )
        try:
            _require_final_paths_absent(final_definition, final_bundle, "pre-wait")
            _wait_until(target.timestamp(), clock=_clock, sleeper=_sleep)
            validate_prepublication_boundary(
                prepared.definition_stage,
                final_definition,
                final_bundle,
                staged_bundle=prepared.bundle_stage,
                wall_clock=datetime.fromtimestamp(_clock(), UTC),
            )
            if (
                prepared.definition_stage.read_bytes() != prepared.definition_raw
                or _tree_digest(prepared.bundle_stage)
                != prepared.bundle_tree_sha256
            ):
                raise CurrentCoverageV24Error(
                    "v24 private stage changed while awaiting publication"
                )
            _require_final_paths_absent(final_definition, final_bundle, "late")
            _promote_staged_pair(
                prepared, final_definition, final_bundle
            )
            if stat.S_IMODE(final_definition.stat().st_mode) != 0o444:
                raise CurrentCoverageV24Error(
                    "v24 final definition must be frozen 0444"
                )
            _assert_final_root_ctimes(
                (final_definition, final_bundle), prepared.generated_at
            )
        except BaseException as primary_error:
            try:
                owned_final_exists = _path_has_identity(
                    final_definition,
                    prepared.definition_identity,
                    directory=False,
                ) or _path_has_identity(
                    final_bundle, prepared.bundle_identity, directory=True
                )
                if not owned_final_exists:
                    if (
                        prepared.bundle_stage.exists()
                        and _tree_digest(prepared.bundle_stage)
                        != prepared.bundle_tree_sha256
                    ):
                        raise CurrentCoverageV24Error(
                            "refusing cleanup of changed v24 private bundle"
                        )
                    _discard_bundle_stage(
                        prepared.bundle_stage,
                        prepared.bundle_identity,
                        prepared.bundle_member_identities,
                    )
                    _discard_file_stage(
                        prepared.definition_stage, prepared.definition_identity
                    )
            except Exception as cleanup_error:
                primary_error.add_note(f"v24 stage cleanup failed: {cleanup_error}")
            raise
    return validate_current_coverage_ledger_v24(
        final_bundle, definition_path=final_definition
    )


def write_v24_definition(
    package_root: str | Path, output_path: str | Path, *, generated_at: str
) -> str:
    """Refuse publication until all downstream and digest fuses are sealed."""

    preflight_v24_publication(package_root)
    raw = make_v24_definition(package_root, generated_at=generated_at)
    if _sha256(raw) != V24_DEFINITION_SHA256:
        raise CurrentCoverageV24Error("v24 definition digest changed")
    destination = Path(os.path.abspath(os.fspath(output_path)))
    if destination.exists() or destination.is_symlink():
        raise CurrentCoverageV24Error(f"refusing existing output: {destination}")
    raise CurrentCoverageV24Error(
        "v24 definition cannot publish alone; use the paired v24 publisher"
    )


def write_current_coverage_ledger_v24(
    definition_path: str | Path,
    output_path: str | Path,
    *,
    freeze: bool = True,
) -> dict[str, Any]:
    if freeze is not True:
        raise CurrentCoverageV24Error("v24 publication requires freeze=True")
    definition = Path(definition_path)
    root = definition.parent.parent.resolve()
    preflight_v24_publication(root)
    if Path(output_path).resolve() != root / V24_BUNDLE_PATH:
        raise CurrentCoverageV24Error("v24 bundle publication path changed")
    raise CurrentCoverageV24Error(
        "v24 bundle cannot publish alone; use the paired v24 publisher"
    )


def validate_current_coverage_ledger_v24(
    output_path: str | Path, *, definition_path: str | Path
) -> dict[str, Any]:
    _require_downstream_pins()
    definition = Path(definition_path).resolve()
    root = definition.parent.parent.resolve()
    output = Path(output_path).resolve()
    if definition != root / V24_DEFINITION_PATH:
        raise CurrentCoverageV24Error("v24 definition publication path changed")
    if output != root / V24_BUNDLE_PATH:
        raise CurrentCoverageV24Error("v24 bundle publication path changed")
    return _validate_v24_bundle(
        output, definition_path=definition, require_live=True
    )


__all__ = [
    "ADDED_ARTIFACTS_SHA256",
    "ADDED_ARTIFACT_IDS",
    "ALL_ENTRIES_SHA256",
    "ARTIFACT_KINDS_V4",
    "ARTIFACT_REPLACEMENTS",
    "BUNDLE_FILES",
    "BUNDLE_FORMAT_V4",
    "CurrentCoverageV24Bundle",
    "CurrentCoverageV24Error",
    "DEFINITION_SCHEMA_VERSION_V4",
    "HISTORICAL_2_SHA256",
    "HISTORICAL_ARTIFACT_IDS",
    "LEDGER_FORMAT_V4",
    "LEDGER_SCHEMA_VERSION_V4",
    "NEW_ARTIFACT_IDS",
    "NON_LEDGER_ARTIFACT_DECISIONS",
    "PENDING_DOWNSTREAM_PIN_BLUEPRINT",
    "PENDING_DOWNSTREAM_REPLACEMENTS",
    "PendingDownstreamPinsError",
    "PARITY_GAPS_SHA256",
    "RECORD_UNITS_V4",
    "REMOVED_8_SHA256",
    "REMOVED_ARTIFACT_IDS",
    "REPLACEMENT_8_SHA256",
    "REPLACEMENT_ARTIFACT_IDS",
    "SCOPE_POLICY",
    "UNCHANGED_40_SHA256",
    "V23_BASE_LINEAGE",
    "V24_BUNDLE_PATH",
    "V24_DEFINITION_PATH",
    "V24_DEFINITION_SHA256",
    "V24_GENERATED_AT",
    "V24_LEDGER_ID",
    "build_current_coverage_ledger_v24",
    "make_v24_definition",
    "pending_downstream_pins",
    "preflight_v24_publication",
    "preview_parity_gaps",
    "preview_v24_delta",
    "publish_current_coverage_v24",
    "validate_current_coverage_ledger_v24",
    "validate_private_staging_boundary",
    "validate_prepublication_boundary",
    "write_current_coverage_ledger_v24",
    "write_v24_definition",
]
