from __future__ import annotations

from copy import deepcopy
import csv
import hashlib
from itertools import zip_longest
import json
from pathlib import Path
import socket
import stat
import tempfile
import unittest
from unittest.mock import patch

from datacenter_atlas import construction_master_v2 as master_v2
from datacenter_atlas.construction_master_v2 import (
    BUNDLE_FILES,
    CORE_ROLE_KEYS,
    NULL_ROLES,
    ConstructionMasterV2Error,
    _canonical_line,
    _role_projection,
    _strip_roles,
    _validate_roles,
    validate_construction_master_v2,
    validate_definition,
    write_construction_master_v2,
)


ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "sources/construction-master-2026-07-20-public-open-v16.json"
BUNDLE = ROOT / "construction_master/2026-07-20-public-open-v16"
BASE_DEFINITION = ROOT / "sources/construction-master-2026-07-19-public-open-v14.json"
BASE_BUNDLE = ROOT / "construction_master/2026-07-19-public-open-v14"
V42_DEFINITION = ROOT / "sources/open-seed-2026-07-20-v42.json"
V42_MANIFEST = ROOT / "releases/2026-07-20-open-seed-v42/manifest.json"
V42_DATA = ROOT / "releases/2026-07-20-open-seed-v42/construction_pipeline.csv"
RECOVERY_ROOT = (
    ROOT
    / "satellite_review_recoveries/2026-07-19-global-open-v3-unknown-033-recovered-25"
)

DEFINITION_SHA256 = "541fddec96e1ef309219ee648d6d9c8fa0e99dbf6db09619d89cb5d05b423be6"
SOURCE_DEFINITION_SHA256 = (
    "58b4ac0160c42ea8a9404936249695997eb66fa3e1d54b9f36246083e3c5ec6f"
)
MANIFEST_SHA256 = "a43846e71f07b4eb9ac10643caf71c907a837537ba1ec994caa70a366e45908f"
BUNDLE_INVENTORY_SHA256 = (
    "5fd8f4b8ace4a0a5e75e12454b34a64f46374ff41e88dbcbcf8117af625b3ab8"
)
BASE_DEFINITION_SHA256 = (
    "2483d9965f47756468776f2e377ad7e25720e858dea8798cf0825448aa3870f4"
)
BASE_MANIFEST_SHA256 = (
    "12cb7e843d264bae9d8637db81ac76988c89e2e3eb926ea1fcc1d43077a8d88b"
)
BASE_BUNDLE_INVENTORY_SHA256 = (
    "4b2ce6298788a6af9b5df90c4148b640fafdcb39ad8c0044d35832b8cd3bee60"
)
OUTPUT_CHECKPOINTS = {
    "ATTRIBUTION.txt": (5814, "efac7562a1daeb179182bec94e5d3b7451f27ccbd6170b9d7cc962fac370e825"),
    "README.md": (1349, "27bb3d59668444751c023bc7a176a04b156cc9b8f19accd3593b52ca45f3a6c8"),
    "construction-master.csv": (189566066, "a44bb0f64c4cdb4d6b215b2bbe8a8032da9ea9f8cef6414fa02a57d94d763644"),
    "construction-master.jsonl": (325247990, "e573deea4314a9edd2148e695489bd0f2cc47fac71530fe09b81b685c678e19c"),
    "coverage.json": (8492, "c1870a0dfa329ae9bd204e623ceaf87f0844d0b1fb811674e19d317fde2fd9cd"),
    "manifest.json": (9667, MANIFEST_SHA256),
    "manifest.sha256": (80, "e1ba9bca61b70b08373673b8bd12ed94fafb7e33ba1ea4425a109071e6787140"),
}
EXPECTED_INVARIANTS = {
    "added_replacement_rows": 63,
    "added_source_record_ids_sha256": "0fd9aa71b3b3292235f7eba7d694d1609ce5a0a28be5d260d10210f7418446a2",
    "base_replaced_rows": 199,
    "base_replaced_source_record_ids_sha256": "f9801441dab6df464741d53f7bfc4e9c664b860e66a5de6797eeef8c82ca1950",
    "base_rows": 109111,
    "inherited_rows": 108912,
    "inherited_rows_without_roles_sha256": "d6580ceaad528c3a6a489eb568368e7109a0488dfa4425bbe100dc0f1f13ac3f",
    "replacement_role_projection_sha256": "85f6aee3a09ed7532169da051607bf943aec19a9cf21739c922e0de67e8d2b97",
    "replacement_rows": 262,
    "replacement_rows_with_any_role": 89,
    "replacement_rows_with_customers": 1,
    "replacement_rows_with_operator": 30,
    "replacement_rows_with_owner": 46,
    "replacement_rows_with_source_role_tags": 50,
    "replacement_rows_with_tenants": 4,
    "replacement_rows_with_users": 36,
    "replacement_rows_without_roles_sha256": "c0e112274bb7be45dcc988953258d8359e715a67ea142a421ca66acbcf7a7f17",
    "replacement_source_record_ids_sha256": "19a28da1b0269404cc81997912a51c8a58e72a44783dba56980b0daa4eba2e16",
    "rows_with_contract_marker": 262,
    "satellite_recovery_control_plane_bytes": 15313,
    "satellite_recovery_rows": 0,
    "tier_a_arithmetic_projection_sha256": "818ec176bdc6e5c181ac65a1fc1e4d5df795fa2cfaeae239a57530588729c403",
    "tier_a_rows": 382,
    "tier_b_rows": 6298,
    "tier_c_rows": 102494,
    "total_rows": 109174,
    "unchanged_replacement_rows": 199,
}
EXPECTED_STATUSES = {
    "None": 4,
    "announced": 3,
    "civil_works": 2,
    "expansion": 27,
    "foundations": 2,
    "imagery_change_candidate_rejected_for_site_promotion": 31,
    "imagery_change_candidate_retained_for_manual_followup": 12,
    "mep_electrical": 15,
    "permit_process_review_lead": 13,
    "permitted": 3,
    "planning_application_review_lead": 139,
    "proposed": 22,
    "proposed_review_lead": 3,
    "review_lead": 6139,
    "shell": 8,
    "site_preparation": 11,
    "structural_construction_signal": 100750,
    "structural_proposed_signal": 1701,
    "under_construction": 289,
}
EXPECTED_KINDS = {
    "fuzzy_identity_lifecycle_review_lead": 6130,
    "official_england_planning_application_review_lead": 3,
    "official_france_igedd_environmental_opinion_review_lead": 4,
    "official_netherlands_koop_permit_review_lead": 13,
    "official_new_zealand_fast_track_review_lead": 3,
    "official_nsw_major_projects_planning_review_lead": 22,
    "official_planning_application_review_lead": 114,
    "osm_planet_structural_candidate": 102451,
    "sec_filing_project_review_lead": 9,
    "sentinel_analyst_change_review": 43,
    "source_construction_pipeline": 382,
}
REJECTED_PATH_FRAGMENTS = {
    "2026-07-20-public-open-v15",
    "2026-07-20-open-seed-v41",
    "epoch-official-open-seed-v41",
}
REJECTED_HASHES = {
    "cf8007a718c7b971daffa8608345abb9bed82f1806a1387556c1dca0c1ce7609",
    "1f2c14858b601c60e511afbe0d359cf78fadafe8f8fcdcd0734fdcc7a639fdca",
    "270400fc4257c078fd77d165b40911c9e852c5511a52b2ed4972b489872e5936",
    "967127f07f0e30be989bfbeba2ab7884a20b4ff570357648af8c48652e67c1b5",
    "e346df3f432ddb4a53fbfe9b4d172d2231a73b631e6b18106b74b49d977a2428",
    "752b605b4d34148370b2871c76bf8a0567187ac470438fdb593804a2c32ec76e",
    "3e333da6306708584f84bf49eeb20a080d60811dde098e945e8d04b1066e2e88",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        digest.update(entry.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256(entry)))
    return digest.hexdigest()


def _rows(path: Path):
    with path.open("rb") as source:
        for raw in source:
            yield json.loads(raw)


class FrozenConstructionMasterV16Tests(unittest.TestCase):
    def _assert_definition_rejected(self, document: dict) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=DEFINITION.parent,
            prefix="changed-v16-master-",
            suffix=".json",
        ) as temporary:
            temporary.write(json.dumps(document, indent=2, sort_keys=True) + "\n")
            temporary.flush()
            with self.assertRaises(ConstructionMasterV2Error):
                validate_definition(temporary.name)

    def test_frozen_bundle_rebuilds_twice_offline_with_rejected_access_guards(self) -> None:
        self.assertEqual(_sha256(DEFINITION), DEFINITION_SHA256)
        self.assertEqual(_sha256(BUNDLE / "manifest.json"), MANIFEST_SHA256)
        self.assertEqual(_inventory_sha256(BUNDLE), BUNDLE_INVENTORY_SHA256)
        self.assertEqual(set(OUTPUT_CHECKPOINTS), BUNDLE_FILES)
        for name, (size, digest) in OUTPUT_CHECKPOINTS.items():
            self.assertEqual((BUNDLE / name).stat().st_size, size)
            self.assertEqual(_sha256(BUNDLE / name), digest)

        original_open = Path.open
        original_checkpoint_spec = master_v2._checkpoint_spec
        prohibited_recovery_names = {
            "inventory.jsonl",
            "selected-queue-jobs.jsonl",
            "source-evidence-manifest-snapshot.json",
        }

        def guarded_open(path: Path, *args, **kwargs):
            resolved = path.resolve()
            rendered = resolved.as_posix()
            if any(fragment in rendered for fragment in REJECTED_PATH_FRAGMENTS):
                raise AssertionError(f"rejected path traversed: {resolved}")
            if RECOVERY_ROOT in resolved.parents and (
                "batch" in resolved.relative_to(RECOVERY_ROOT).parts
                or resolved.name in prohibited_recovery_names
            ):
                raise AssertionError(f"recovery payload traversed: {resolved}")
            return original_open(path, *args, **kwargs)

        def guarded_checkpoint_spec(package_root, spec, label):
            rendered = str(spec.get("path", ""))
            if any(fragment in rendered for fragment in REJECTED_PATH_FRAGMENTS):
                raise AssertionError(f"rejected checkpoint path: {rendered}")
            if spec.get("sha256") in REJECTED_HASHES:
                raise AssertionError(f"rejected checkpoint hash: {spec['sha256']}")
            return original_checkpoint_spec(package_root, spec, label)

        blocked = AssertionError("offline build attempted network or DNS access")
        with tempfile.TemporaryDirectory(
            prefix="construction-master-v16-test-", dir="/private/tmp"
        ) as temporary, patch.object(
            Path, "open", guarded_open
        ), patch.object(
            master_v2, "_checkpoint_spec", side_effect=guarded_checkpoint_spec
        ), patch.object(
            socket, "socket", side_effect=blocked
        ), patch.object(
            socket, "create_connection", side_effect=blocked
        ), patch.object(
            socket, "getaddrinfo", side_effect=blocked
        ):
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            write_construction_master_v2(DEFINITION, first)
            write_construction_master_v2(DEFINITION, second)
            validate_construction_master_v2(
                BUNDLE, definition_path=DEFINITION, reproduce=False
            )
            for name in sorted(BUNDLE_FILES):
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
                self.assertEqual((first / name).read_bytes(), (BUNDLE / name).read_bytes())

        self.assertEqual(stat.S_IMODE(BUNDLE.stat().st_mode), 0o555)
        self.assertTrue(
            all(stat.S_IMODE(entry.stat().st_mode) == 0o444 for entry in BUNDLE.iterdir())
        )

    def test_direct_v14_v42_lineage_and_legacy_v14_bytes_are_exact(self) -> None:
        definition = json.loads(DEFINITION.read_text())
        self.assertEqual(
            set(definition["inputs"]),
            {"base_master", "replacement_release", "satellite_recovery_acceptance"},
        )
        base = definition["inputs"]["base_master"]
        self.assertEqual(base["master_id"], "2026-07-19-public-open-v14")
        self.assertEqual(base["definition"]["sha256"], BASE_DEFINITION_SHA256)
        self.assertEqual(base["manifest"]["sha256"], BASE_MANIFEST_SHA256)
        self.assertEqual(
            base["jsonl"]["sha256"],
            "81aa4730739897134a280933877d28990b8308e0526c4bf383bf18c4ed6242af",
        )
        replacement = definition["inputs"]["replacement_release"]
        self.assertEqual(replacement["artifact_id"], "epoch-official-open-seed-v42")
        self.assertEqual(replacement["release_id"], "epoch-official-open-seed-v42")
        self.assertEqual(replacement["definition"]["bytes"], 48406)
        self.assertEqual(replacement["definition"]["sha256"], SOURCE_DEFINITION_SHA256)
        self.assertEqual(_sha256(V42_DEFINITION), SOURCE_DEFINITION_SHA256)
        self.assertEqual(
            replacement["manifest"]["sha256"],
            "049506e5caee0e2efd0a6cadd7fb71cec0bfd7d647d4c74e047f69dfe0c30680",
        )

        self.assertEqual(_sha256(BASE_DEFINITION), BASE_DEFINITION_SHA256)
        self.assertEqual(_sha256(BASE_BUNDLE / "manifest.json"), BASE_MANIFEST_SHA256)
        self.assertEqual(_inventory_sha256(BASE_BUNDLE), BASE_BUNDLE_INVENTORY_SHA256)

        retained_runtime = Path(master_v2.__file__).read_text() + DEFINITION.read_text()
        manifest_text = (BUNDLE / "manifest.json").read_text()
        for forbidden in REJECTED_PATH_FRAGMENTS | REJECTED_HASHES:
            self.assertNotIn(forbidden, retained_runtime)
            self.assertNotIn(forbidden, manifest_text)

    def test_exact_counts_digests_recovery_and_no_census_claim(self) -> None:
        coverage = json.loads((BUNDLE / "coverage.json").read_text())
        manifest = json.loads((BUNDLE / "manifest.json").read_text())
        self.assertEqual(coverage["replacement_invariants"], EXPECTED_INVARIANTS)
        self.assertNotIn("v15_invariants", coverage)
        self.assertEqual(
            coverage["replacement"],
            {
                "added_rows": 63,
                "base_artifact_id": "epoch-official-open-seed-v33",
                "base_rows_replaced": 199,
                "publication_contract_version": 4,
                "replacement_artifact_id": "epoch-official-open-seed-v42",
                "replacement_rows": 262,
                "unchanged_source_record_ids": 199,
            },
        )
        self.assertEqual(
            coverage["role_counts"],
            {
                "rows_with_any_role": 89,
                "rows_with_contract_marker": 262,
                "rows_with_source_role_tags": 50,
                "with_core_role": {
                    "customers": 1,
                    "operator": 30,
                    "owner": 46,
                    "tenants": 4,
                    "users": 36,
                },
            },
        )
        row_counts = coverage["row_counts"]
        self.assertEqual(row_counts["total"], 109174)
        self.assertEqual(row_counts["by_tier"], {"A": 382, "B": 6298, "C": 102494})
        self.assertEqual(row_counts["by_normalized_status"], EXPECTED_STATUSES)
        self.assertEqual(row_counts["by_observation_kind"], EXPECTED_KINDS)
        self.assertEqual(
            row_counts["by_source_artifact"]["epoch-official-open-seed-v42"], 262
        )
        self.assertNotIn("epoch-official-open-seed-v33", row_counts["by_source_artifact"])
        self.assertIsNone(row_counts["unique_physical_site_count"])
        self.assertEqual(manifest["row_counts"], row_counts)
        self.assertEqual(manifest["generated_at"], "2026-07-20T06:00:00Z")

        recovery = coverage["satellite_recovery_acceptance"]
        self.assertEqual(recovery["control_plane_files"], 4)
        self.assertEqual(recovery["control_plane_bytes"], 15313)
        self.assertEqual(recovery["rows_created"], 0)
        self.assertFalse(recovery["payload_traversed"])
        self.assertFalse(recovery["source_batch_promoted"])
        self.assertFalse(recovery["imagery_inference_created"])
        recovery_paths = [
            item["path"]
            for item in manifest["input_checkpoints"]
            if "satellite_recovery_acceptance" in item["label"]
        ]
        self.assertEqual(len(recovery_paths), 4)
        self.assertFalse(any("/batch/" in path for path in recovery_paths))

        self.assertFalse(coverage["scope"]["global_completeness_claimed"])
        self.assertIsNone(coverage["scope"]["unique_physical_site_count"])
        readme = (BUNDLE / "README.md").read_text().lower()
        self.assertIn("not a deduplicated physical-site census", readme)
        self.assertIn("claims no global completeness", readme)

    def test_exact_v42_roles_and_v14_only_inherited_baseline(self) -> None:
        with V42_DATA.open(newline="", encoding="utf-8") as source:
            source_rows = list(csv.DictReader(source))
        source_by_id = {row["entity_id"]: row for row in source_rows}
        self.assertEqual(len(source_by_id), 262)

        master_rows = _rows(BUNDLE / "construction-master.jsonl")
        replacement_rows = [next(master_rows) for _ in range(262)]
        role_digest = hashlib.sha256()
        replacement_digest = hashlib.sha256()
        role_presence = {key: 0 for key in CORE_ROLE_KEYS}
        rows_with_any_role = 0
        rows_with_source_role_tags = 0
        for row in replacement_rows:
            record_id = row["source"]["record_id"]
            source = source_by_id[record_id]
            tags = json.loads(source["tags_json"])
            expected_roles = {
                "source_publication_contract_version": 4,
                **{key: source[key] or None for key in CORE_ROLE_KEYS},
                "source_role_tags": {
                    key: value for key, value in tags.items() if key.startswith("role:")
                },
            }
            self.assertEqual(row["roles"], expected_roles)
            self.assertEqual(row["source"]["artifact_id"], "epoch-official-open-seed-v42")
            role_digest.update(_canonical_line(_role_projection(record_id, expected_roles)))
            replacement_digest.update(_canonical_line(_strip_roles(row)))
            any_role = bool(expected_roles["source_role_tags"])
            for key in CORE_ROLE_KEYS:
                role_presence[key] += expected_roles[key] is not None
                any_role = any_role or expected_roles[key] is not None
            rows_with_any_role += any_role
            rows_with_source_role_tags += bool(expected_roles["source_role_tags"])
        self.assertEqual(
            role_digest.hexdigest(), EXPECTED_INVARIANTS["replacement_role_projection_sha256"]
        )
        self.assertEqual(
            replacement_digest.hexdigest(),
            EXPECTED_INVARIANTS["replacement_rows_without_roles_sha256"],
        )
        self.assertEqual(
            role_presence,
            {"owner": 46, "operator": 30, "users": 36, "tenants": 4, "customers": 1},
        )
        self.assertEqual(rows_with_any_role, 89)
        self.assertEqual(rows_with_source_role_tags, 50)

        base_rows = _rows(BASE_BUNDLE / "construction-master.jsonl")
        base_replaced = [next(base_rows) for _ in range(199)]
        base_ids = {row["source"]["record_id"] for row in base_replaced}
        replacement_ids = {row["source"]["record_id"] for row in replacement_rows}
        self.assertEqual(len(replacement_ids - base_ids), 63)
        self.assertEqual(base_ids - replacement_ids, set())

        inherited_digest = hashlib.sha256()
        sentinel = object()
        inherited_count = 0
        for base_row, current_row in zip_longest(
            base_rows, master_rows, fillvalue=sentinel
        ):
            self.assertIsNot(base_row, sentinel)
            self.assertIsNot(current_row, sentinel)
            self.assertEqual(current_row["roles"], NULL_ROLES)
            self.assertEqual(_strip_roles(current_row), base_row)
            inherited_digest.update(_canonical_line(base_row))
            inherited_count += 1
        self.assertEqual(inherited_count, 108912)
        self.assertEqual(
            inherited_digest.hexdigest(),
            EXPECTED_INVARIANTS["inherited_rows_without_roles_sha256"],
        )

    def test_definition_lineage_mutations_fail_closed(self) -> None:
        original = json.loads(DEFINITION.read_text())
        mutations: list[tuple[str, dict]] = []

        changed = deepcopy(original)
        changed["inputs"]["base_master"]["master_id"] = "wrong-base"
        mutations.append(("base id", changed))
        changed = deepcopy(original)
        changed["inputs"]["base_master"]["jsonl"]["path"] = "sources/open-seed-2026-07-20-v42.json"
        mutations.append(("base path", changed))
        changed = deepcopy(original)
        changed["inputs"]["base_master"]["jsonl"]["sha256"] = "0" * 64
        mutations.append(("base hash", changed))
        changed = deepcopy(original)
        changed["inputs"]["replacement_release"]["artifact_id"] = "wrong-replacement"
        mutations.append(("replacement id", changed))
        changed = deepcopy(original)
        changed["inputs"]["replacement_release"]["data"]["path"] = "sources/open-seed-2026-07-20-v42.json"
        mutations.append(("replacement path", changed))
        changed = deepcopy(original)
        changed["inputs"]["replacement_release"]["data"]["sha256"] = "0" * 64
        mutations.append(("replacement hash", changed))
        changed = deepcopy(original)
        changed["inputs"]["replacement_release"]["definition"]["sha256"] = "0" * 64
        mutations.append(("source definition checkpoint", changed))
        changed = deepcopy(original)
        changed["inputs"]["unexpected_lane"] = {}
        mutations.append(("unexpected input lane", changed))
        changed = deepcopy(original)
        changed["inputs"]["satellite_recovery_acceptance"]["batch_manifest"] = {
            "bytes": 6468769,
            "path": "satellite_review_recoveries/2026-07-19-global-open-v3-unknown-033-recovered-25/batch/batch-manifest.json",
            "sha256": "797ef873d519b9a8e503cf4ad79231d0ca42ea50fcf9159b65db8993a2322c7d",
        }
        mutations.append(("recovery payload lane", changed))

        for label, document in mutations:
            with self.subTest(label=label):
                self._assert_definition_rejected(document)

    def test_contract_marker_requires_exact_built_in_int_at_every_gate(self) -> None:
        definition = json.loads(DEFINITION.read_text())
        missing = object()
        invalid_markers = (3, 4.0, True, "4", None, missing)
        for marker in invalid_markers:
            changed = deepcopy(definition)
            replacement = changed["inputs"]["replacement_release"]
            if marker is missing:
                replacement.pop("publication_contract_version")
            else:
                replacement["publication_contract_version"] = marker
            with self.subTest(gate="definition", marker=repr(marker)):
                self._assert_definition_rejected(changed)

        replacement = definition["inputs"]["replacement_release"]
        manifest_path = (ROOT / replacement["manifest"]["path"]).resolve()
        source_definition_path = (ROOT / replacement["definition"]["path"]).resolve()
        original_json_file = master_v2._json_file
        semantic_gates = (
            ("release_manifest", manifest_path, lambda document: document),
            ("source_definition", source_definition_path, lambda document: document),
            (
                "source_expected_release",
                source_definition_path,
                lambda document: document["expected_release"],
            ),
        )
        for gate, target_path, select in semantic_gates:
            for marker in invalid_markers:
                def changed_json_file(path, label, *, marker=marker):
                    document, raw = original_json_file(path, label)
                    if Path(path).resolve() == target_path:
                        document = deepcopy(document)
                        target = select(document)
                        if marker is missing:
                            target.pop("publication_contract_version")
                        else:
                            target["publication_contract_version"] = marker
                    return document, raw

                with self.subTest(gate=gate, marker=repr(marker)), patch.object(
                    master_v2, "_json_file", side_effect=changed_json_file
                ):
                    with self.assertRaises(ConstructionMasterV2Error):
                        validate_definition(DEFINITION)

        valid_roles = dict(NULL_ROLES)
        valid_roles["source_publication_contract_version"] = 4
        _validate_roles(valid_roles, marked=True)
        for marker in invalid_markers:
            changed_roles = dict(valid_roles)
            if marker is missing:
                changed_roles.pop("source_publication_contract_version")
            else:
                changed_roles["source_publication_contract_version"] = marker
            with self.subTest(gate="row_roles", marker=repr(marker)):
                with self.assertRaises(ConstructionMasterV2Error):
                    _validate_roles(changed_roles, marked=True)


if __name__ == "__main__":
    unittest.main()
