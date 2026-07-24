from __future__ import annotations

from contextlib import ExitStack
import csv
import hashlib
import json
from pathlib import Path
import socket
import stat
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "source_artifacts/gap-region-official-discovery-2026-07-21-v1"
V68_DEFINITION = ROOT / "sources/open-seed-2026-07-21-v68.json"
V68_MANIFEST = ROOT / "releases/2026-07-21-open-seed-v68/manifest.json"
V68_ENTITIES = ROOT / "releases/2026-07-21-open-seed-v68/entities.csv"

TARGET_COUNTRIES = {
    "Egypt",
    "Ghana",
    "Rwanda",
    "Uganda",
    "Zambia",
    "Angola",
    "Algeria",
    "Tunisia",
    "Jordan",
    "Kuwait",
}

ARTIFACT_FILE_SPECS = {
    "README.md": (
        5281,
        "abdec74e4cb13b217e3dae123b684bbbed80b85e8c2f77e3627f64eb1c2a22a3",
    ),
    "identity-and-capacity-guardrails.json": (
        3547,
        "5b59b67788e60456eb92c67335ca568ca54ec088542de20b8945eda325835213",
    ),
    "manifest.json": (
        1416,
        "39f7bc33d99e9f65bddbb32cff711c2d784e7abb6d783afe9824e4a37da6d123",
    ),
    "manifest.sha256": (
        80,
        "03e37e8bb88785417b59f303976adcf4cf55dc165b063c8fe7f278e2cde2b2ca",
    ),
    "retrieval-inventory.json": (
        15512,
        "a364efb78a7d4c09186266f5a39c0c7f8b9a3af056d9cfa2da8afc31888fffff",
    ),
    "rights-and-disposition.json": (
        1479,
        "ce2bf2bee2dae615ab085bf386d7ef726835e337fb62fd3daabcb7df20a274b1",
    ),
    "source-snapshot.json": (
        6225,
        "bf1f8743efb3d421c02496531a45dc29be490f94453d40efc2e79812810f4ea8",
    ),
}

CAPTURE_SPECS = {
    "ghana_adc": {
        "status": 200,
        "exit": 0,
        "body": (
            114974,
            "d001cd8845e625b3934c7dae7b96c4c7948c8d6dbdbd236372e0d337add37659",
        ),
        "headers": (
            486,
            "c244dcbec4d5dd5349a83ad432709ac98104c99b33724a03353cbb7c8bc08bf1",
        ),
        "writeout": (
            16620,
            "c0aa686af654351ffa2573897955c665c7a2fb150a92b4c66580c474b1de53f0",
        ),
    },
    "egypt_raya": {
        "status": 200,
        "exit": 0,
        "body": (
            80478,
            "3f7d9b6d4483afd19eca97b3766299defc89664b25d869fba9d4e58a41b212f5",
        ),
        "headers": (
            1069,
            "63da4b05c4aeac4e91f5b54211c926e13fa8b078d59ddce53cac9886f3b2cf44",
        ),
        "writeout": (
            9774,
            "e3c64b5913ba198ca4ff6b523f9c1cdd867f9bc76c4bd35177046c8c089ed27d",
        ),
    },
    "rwanda_kic": {
        "status": 200,
        "exit": 0,
        "body": (
            28653,
            "b2ca98d9b5803e2fe1a3f4e3f6505c20221da3afb3f20de071ae02f6c947dee3",
        ),
        "headers": (
            2610,
            "01be628cef0a47dc5ffeafbe943211afb19126982a2bf48d68d7e7664a36cd53",
        ),
        "writeout": (
            16654,
            "f2f1dc0e01c01956911d618137ce2ffb02d7b7f81cfaf6997b5e7c1bdef89834",
        ),
    },
    "uganda_nita_study": {
        "status": 200,
        "exit": 0,
        "body": (
            60277,
            "4635b5b1728abef55b5d92d249e9e188c8ea5eaa063419f765c1afaff3c19847",
        ),
        "headers": (
            989,
            "1053c55290d446ad2a92e04bec37208737e75cdff53df95b9b0a3d1c3a7a52d2",
        ),
        "writeout": (
            9681,
            "d42e463fef78679567649416acb7207206220e597fe2afcec779f85c100a684d",
        ),
    },
    "zambia_huawei_mou": {
        "status": 200,
        "exit": 0,
        "body": (
            126461,
            "2f8d81861b6894b89c4d830bef0cecfeb08aceda0048af07a440400520a81292",
        ),
        "headers": (
            563,
            "d374a7ed6afa76acd40c32fe4df5b3ac6117aaabaff1c20f523c651f551a9e19",
        ),
        "writeout": (
            8910,
            "d68e353f73688bfe122bea840cf998ae45e199a9bfa8eb1ac4f68be16bd087e8",
        ),
    },
    "angola_paratus": {
        "status": 200,
        "exit": 0,
        "body": (
            402496,
            "490bbfc462bf3ffe3ec1e821c9e6be5163782dcb0fc246529917c7f6398e127f",
        ),
        "headers": (
            201,
            "db46517a17e3fe6ddd24fcb55dc2de2a27f93aade79e15184521c4b635c54bff",
        ),
        "writeout": (
            11077,
            "18b8ed774bfad82c1a28708a3854fca7704ec24b328ebc4742dff04ab33cf4c2",
        ),
    },
    "algeria_national_dc": {
        "status": 200,
        "exit": 0,
        "body": (
            112392,
            "d85c8535df2747227820b861708e63f4c582ed808fc59f409797cfb376c8b8fa",
        ),
        "headers": (
            1119,
            "b14fac4350966fad24deb70aeaba38e1e1b4fc4ae85c1dabbb663718c02a83dd",
        ),
        "writeout": (
            19364,
            "98cb17e82f29393529f7ff54f5d06d8cdf227c897d645927a98c7b695bb44c29",
        ),
    },
    "tunisia_tender": {
        "status": 0,
        "exit": 60,
        "body": None,
        "headers": (
            0,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
        "writeout": (
            1630,
            "3de447f18e6af4a754953dbd99f18f717c1deb4c2c36da7a5c9ae523715f48b5",
        ),
    },
    "kuwait_google_region": {
        "status": 200,
        "exit": 0,
        "body": (
            225359,
            "91fb4cd415a898879f97889557ab5518a4f738281f9954ad5bbb5a844727aa83",
        ),
        "headers": (
            1990,
            "e3683f11474e7757e4bdc66979b41dbc3515f0ae9d08815c190781444a26841c",
        ),
        "writeout": (
            12459,
            "03f2f9c455999f1d3693b67b13fcbb217c33311666fdc6712d21be0b402b7166",
        ),
    },
    "jordan_damamax": {
        "status": 200,
        "exit": 0,
        "body": (
            197711,
            "18dba857d3d1e62eba78c767778d41a80d51a1f7703189cdd172ec88ceeed775",
        ),
        "headers": (
            779,
            "cd32815cfd55a3860af4776f15a6f8cbb7f378889ae8855bc24479560f6b3e40",
        ),
        "writeout": (
            10516,
            "18170bd074c05909cadbc097e08cb8a3642d123a48f3ef322825795f0ea1fbb2",
        ),
    },
}


def sha256(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


class GapRegionOfficialDiscoveryTests(unittest.TestCase):
    def _offline(self) -> ExitStack:
        stack = ExitStack()
        failure = AssertionError("gap-region artifact replay attempted network access")
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, name, side_effect=failure))
        return stack

    def test_artifact_is_closed_canonical_frozen_and_byte_pinned(self) -> None:
        self.assertTrue(ARTIFACT.is_dir())
        self.assertFalse(ARTIFACT.is_symlink())
        self.assertEqual(stat.S_IMODE(ARTIFACT.stat().st_mode), 0o555)
        self.assertEqual(
            {file_path.name for file_path in ARTIFACT.iterdir() if file_path.is_file()},
            set(ARTIFACT_FILE_SPECS),
        )
        for name, expected in ARTIFACT_FILE_SPECS.items():
            file_path = ARTIFACT / name
            self.assertFalse(file_path.is_symlink())
            self.assertTrue(stat.S_ISREG(file_path.stat().st_mode))
            self.assertEqual(stat.S_IMODE(file_path.stat().st_mode), 0o444)
            self.assertEqual((len(file_path.read_bytes()), sha256(file_path)), expected)
            if file_path.suffix == ".json":
                text = file_path.read_text(encoding="utf-8")
                self.assertEqual(
                    text,
                    json.dumps(json.loads(text), indent=2, ensure_ascii=False) + "\n",
                )

        manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["closed_file_set"]), set(ARTIFACT_FILE_SPECS))
        self.assertEqual(manifest["curated_source_records"], 0)
        for row in manifest["files"]:
            file_path = ARTIFACT / row["path"]
            self.assertEqual(
                (len(file_path.read_bytes()), sha256(file_path)),
                (row["bytes"], row["sha256"]),
            )
        tree_payload = json.dumps(manifest["files"], indent=2, sort_keys=True) + "\n"
        self.assertEqual(
            hashlib.sha256(tree_payload.encode()).hexdigest(),
            manifest["tree_sha256"],
        )
        self.assertEqual(
            manifest["tree_sha256"],
            "b8d0f7bd51fa6208c7382ccf241a161498a8befe4d342729da3b8321cdaa5903",
        )
        self.assertEqual(
            (ARTIFACT / "manifest.sha256").read_text(encoding="utf-8"),
            f"{ARTIFACT_FILE_SPECS['manifest.json'][1]}  manifest.json\n",
        )

    def test_zero_promotion_snapshot_replays_deterministically_offline(self) -> None:
        def replay() -> tuple[object, ...]:
            snapshot = json.loads(
                (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
            )
            guardrails = json.loads(
                (ARTIFACT / "identity-and-capacity-guardrails.json").read_text(
                    encoding="utf-8"
                )
            )
            return (
                tuple(snapshot["searched_country_scope"]),
                tuple(
                    (row["country"], row["decision"], row["request_id"])
                    for row in snapshot["bounded_discovery_exclusions"]
                ),
                tuple(sorted(snapshot["totals"].items())),
                tuple(guardrails["result"]["campus_stable_keys"]),
                tuple(guardrails["result"]["project_stable_keys"]),
                tuple(guardrails["result"]["evidence_keys"]),
            )

        with self._offline():
            first = replay()
            second = replay()
        self.assertEqual(first, second)
        self.assertEqual(set(first[0]), TARGET_COUNTRIES)
        self.assertEqual(len(first[1]), 10)
        self.assertTrue(all(value == 0 for _, value in first[2]))
        self.assertEqual(first[3:], ((), (), ()))

    def test_rejection_predicates_preserve_physical_and_identity_boundaries(self) -> None:
        snapshot = json.loads(
            (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        )
        decisions = {
            row["country"]: row["decision"]
            for row in snapshot["bounded_discovery_exclusions"]
        }
        self.assertEqual(
            decisions,
            {
                "Ghana": "scheduled_future_start_not_physical",
                "Egypt": "financing_and_scheduled_start_not_physical",
                "Rwanda": "physical_project_not_identified_as_data_center",
                "Uganda": "market_study_not_physical",
                "Zambia": "mou_and_co_investment_not_physical",
                "Angola": "historical_future_statement_current_unknown",
                "Algeria": "not_current_build",
                "Tunisia": "capture_failed_not_evidence",
                "Kuwait": "cloud_region_plan_not_site_or_physical",
                "Jordan": "operational_service_page_not_current_build",
            },
        )
        self.assertEqual(snapshot["source_records"], [])
        self.assertEqual(snapshot["release_integration"], "none")
        self.assertEqual(snapshot["open_seed_integration"], "none")
        self.assertEqual(snapshot["downstream_product_integration"], "none")
        self.assertEqual(snapshot["source_ledger_integration"], "none")

        guardrails = json.loads(
            (ARTIFACT / "identity-and-capacity-guardrails.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(guardrails["promotion_gate"]["candidate_count_reviewed"], 10)
        self.assertEqual(guardrails["promotion_gate"]["candidate_count_promoted"], 0)
        self.assertIn(
            "groundbreaking",
            guardrails["promotion_gate"]["accepted_physical_milestones"],
        )
        self.assertIn(
            "procurement_or_tender",
            guardrails["promotion_gate"]["excluded_without_physical_observation"],
        )
        self.assertTrue(guardrails["identity_guardrails"]["no_role_inference"])
        self.assertTrue(guardrails["identity_guardrails"]["no_coordinate_inference"])

    def test_power_basis_and_stage_guardrails_create_no_estimates(self) -> None:
        guardrails = json.loads(
            (ARTIFACT / "identity-and-capacity-guardrails.json").read_text(
                encoding="utf-8"
            )
        )
        power = guardrails["power_guardrails"]
        self.assertTrue(power["generation_is_not_load"])
        self.assertTrue(power["mva_is_not_mw"])
        self.assertTrue(power["untyped_mw_remains_untyped"])
        self.assertTrue(power["no_capacity_estimates_created"])
        self.assertEqual(len(power["unpromoted_reported_mentions"]), 2)
        for row in power["unpromoted_reported_mentions"]:
            self.assertIsNone(row["normalized_metric"])
            self.assertIsNone(row["normalized_stage"])
        result = guardrails["result"]
        self.assertEqual(result["capacity_estimates"], [])
        self.assertEqual(result["operating_model_observations"], [])
        self.assertEqual(result["workload_observations"], [])

    def test_capture_inventory_and_recoverable_raw_hashes_are_exact(self) -> None:
        inventory = json.loads(
            (ARTIFACT / "retrieval-inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            (
                inventory["direct_request_attempts"],
                inventory["completed_response_requests"],
                inventory["successful_http_requests"],
                inventory["failed_http_requests"],
                inventory["evidence_supporting_captures"],
                inventory["promoted_source_records"],
            ),
            (10, 9, 9, 1, 0, 0),
        )
        self.assertFalse(inventory["request_credentials_supplied"])
        self.assertFalse(inventory["browser_session_used"])
        self.assertFalse(inventory["tls_verification_disabled"])
        self.assertTrue(inventory["temporary_capture_directory_moved_to_trash"])
        original = Path(inventory["temporary_capture_directory_original_path"])
        trash = Path(inventory["temporary_capture_trash_path"])
        self.assertFalse(original.exists())
        self.assertTrue(trash.is_dir())
        self.assertEqual(trash.name, "dc-gap-regions-20260721.2FfI4G")

        requests = {row["request_id"]: row for row in inventory["controlled_http_requests"]}
        self.assertEqual(set(requests), set(CAPTURE_SPECS))
        expected_raw_names: set[str] = set()
        for request_id, spec in CAPTURE_SPECS.items():
            request = requests[request_id]
            self.assertFalse(request["contributes_evidence"])
            self.assertEqual(request["evidence_keys"], [])
            self.assertEqual(request["http_status"], spec["status"])
            self.assertEqual(request["curl_exit_code"], spec["exit"])
            for suffix, inventory_key, spec_key in (
                ("headers", "headers", "headers"),
                ("writeout.json", "curl_writeout", "writeout"),
            ):
                file_path = trash / f"{request_id}.{suffix}"
                expected_raw_names.add(file_path.name)
                self.assertEqual(
                    (len(file_path.read_bytes()), sha256(file_path)),
                    spec[spec_key],
                )
                self.assertEqual(
                    (request[inventory_key]["bytes"], request[inventory_key]["sha256"]),
                    spec[spec_key],
                )

            body_path = trash / f"{request_id}.body"
            if spec["body"] is None:
                self.assertFalse(body_path.exists())
                self.assertFalse(request["body"]["present"])
                self.assertIsNone(request["body"]["sha256"])
            else:
                expected_raw_names.add(body_path.name)
                self.assertEqual(
                    (len(body_path.read_bytes()), sha256(body_path)), spec["body"]
                )
                self.assertEqual(
                    (request["body"]["bytes"], request["body"]["sha256"]),
                    spec["body"],
                )
                self.assertTrue(request["body"]["present"])

            writeout = json.loads(
                (trash / f"{request_id}.writeout.json").read_text(encoding="utf-8")
            )
            self.assertEqual(writeout["exitcode"], spec["exit"])
            self.assertEqual(writeout["http_code"], spec["status"])
            self.assertEqual(writeout["url_effective"], request["effective_url"])

        self.assertEqual(
            {file_path.name for file_path in trash.iterdir() if file_path.is_file()},
            expected_raw_names,
        )
        self.assertEqual(len(expected_raw_names), 29)
        forbidden_suffixes = {".body", ".headers", ".html", ".pdf", ".png", ".jpg"}
        self.assertTrue(
            all(file_path.suffix not in forbidden_suffixes for file_path in ARTIFACT.iterdir())
        )

    def test_v68_non_mutation_gap_baseline_and_no_collision_are_exact(self) -> None:
        snapshot = json.loads(
            (ARTIFACT / "source-snapshot.json").read_text(encoding="utf-8")
        )
        witness = snapshot["frozen_v68_non_mutation_witness"]
        self.assertEqual(
            (len(V68_DEFINITION.read_bytes()), sha256(V68_DEFINITION)),
            (witness["definition_bytes"], witness["definition_sha256"]),
        )
        self.assertEqual(
            (len(V68_MANIFEST.read_bytes()), sha256(V68_MANIFEST)),
            (witness["release_manifest_bytes"], witness["release_manifest_sha256"]),
        )
        definition = json.loads(V68_DEFINITION.read_text(encoding="utf-8"))
        manifest = json.loads(V68_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(len(definition["curated_inputs"]), 391)
        self.assertEqual(manifest["entities"], 806)
        self.assertEqual(manifest["entities_by_kind"], {"campus": 425, "project": 381})
        self.assertFalse(witness["new_source_paths_selected_by_v68"])
        self.assertEqual(witness["proposed_source_paths"], [])
        self.assertEqual(witness["proposed_stable_key_collisions"], 0)
        self.assertEqual(witness["proposed_evidence_key_collisions"], 0)

        with V68_ENTITIES.open(newline="", encoding="utf-8") as handle:
            countries = {row["country"] for row in csv.DictReader(handle)}
        self.assertTrue(TARGET_COUNTRIES.isdisjoint(countries))
        self.assertEqual(snapshot["v68_baseline"]["target_country_entity_rows"], 0)

        artifact_mentions = []
        for source_file in (ROOT / "sources").glob("*.json"):
            if "gap-region-official-discovery-2026-07-21-v1" in source_file.read_text(
                encoding="utf-8"
            ):
                artifact_mentions.append(source_file.name)
        self.assertEqual(artifact_mentions, [])


if __name__ == "__main__":
    unittest.main()
