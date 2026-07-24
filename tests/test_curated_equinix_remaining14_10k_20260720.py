from __future__ import annotations

import hashlib
import json
import socket
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from datacenter_atlas.curated import CuratedOfficialSourceAdapter
from datacenter_atlas.database import initialize
from datacenter_atlas.service import export_geojson, validate_database


ROOT = Path(__file__).resolve().parents[1]
RETRIEVED_AT = "2026-07-20T02:20:07Z"
AS_OF_DATE = "2025-12-31"
PRIMARY_URL = (
    "https://www.sec.gov/Archives/edgar/data/1101239/"
    "000110123926000075/EQIXAnnualRpt2025PRINT.pdf"
)
BODY_SHA256 = "2fdbe45af04ff1513a1dba3851cf3ed4d181edbf2561e193176e728a3437760c"
BODY_BYTES = 12_696_866
HEADERS_SHA256 = (
    "4d8e5dc4b2123868027f592e72a52631bb49d601c8e430e64439008de1a1b205"
)
HEADERS_BYTES = 686
WRITEOUT_SHA256 = (
    "61af1bfe6e2b2b9a8dfa71f869e7b90c85ccd10154b1bfe1081297a9e09ae3ae"
)
WRITEOUT_BYTES = 15_157
EVIDENCE_KEY = (
    "equinix-2025-annual-report-fourteen-remaining-table-rows-ars-pdf-sec-"
    "captured-2026-07-20"
)
COMPLETE_SUBMISSION_EVIDENCE_KEY = (
    "equinix-2025-form-10-k-americas-eight-complete-submission-sec-"
    "captured-2026-07-20"
)
COMPLETE_SUBMISSION_BODY_SHA256 = (
    "08404c4984e2dc86e78f64580e14277c727d8d49a2de87a303267ed6661497d4"
)
INLINE_XBRL_BODY_SHA256 = (
    "a42a95fc909577bf85b6be6545d046f6938cd6398a66bb0e45379c70b5d82d54"
)
PRIOR_INLINE_XBRL_EVIDENCE_KEYS = [
    "equinix-2025-form-10-k-construction-table-captured-2026-07-19",
    "equinix-2025-form-10-k-lg4-bk1-jh2-sg6-construction-table-captured-2026-07-19",
]
CORROBORATION_GROUP_ID = (
    "equinix-sec-0001101239-26-000032-construction-table-2025-12-31"
)
RAW_EVIDENCE_BYTES = 13_970
RAW_EVIDENCE_SHA256 = (
    "309ad53750d905b5aa75406207ef236bb139e57c87225357e28b06b6cdcf2711"
)


def _row(
    property_name: str,
    location: str,
    quarter: str,
    cabinets: int,
    capex: int,
) -> dict[str, Any]:
    return {
        "property": property_name,
        "location": location,
        "target_open_quarter": quarter,
        "sellable_cabinets": cabinets,
        "approximate_total_capex_usd_millions": capex,
    }


EXPECTED_NEW_ROWS = [
    _row("NY11 phase 5", "New York", "Q1 2026", 600, 38),
    _row("BG2 phase 2", "Bogotá", "Q2 2026", 550, 28),
    _row("SV18 phase 1", "Silicon Valley", "Q2 2026", 2100, 260),
    _row("LG3 phase 1", "Lagos", "Q1 2026", 225, 22),
    _row("DX3 phase 2", "Dubai", "Q2 2026", 800, 81),
    _row("MD5 phase 1", "Madrid", "Q2 2026", 1650, 115),
    _row("HK6 phase 1", "Hong Kong", "Q1 2026", 1000, 124),
    _row("OS3 phase 4", "Osaka", "Q1 2026", 550, 30),
    _row("JK1 phase 2", "Jakarta", "Q4 2026", 1125, 39),
    _row("SY5 phase 4", "Sydney", "Q1 2027", 1350, 96),
    _row("KL2 phases 1 and 2", "Kuala Lumpur", "Q2 2027", 2200, 192),
    _row("MB3 phase 2", "Mumbai", "Q2 2027", 1375, 38),
    _row("CN1 phase 2", "Chennai", "Q4 2027", 1375, 88),
    _row("OS6 phase 1", "Osaka", "Q4 2028", 1850, 355),
]

EXPECTED_FULL_TABLE_ROWS = [
    _row("NY11 phase 5", "New York", "Q1 2026", 600, 38),
    _row("BG2 phase 2", "Bogotá", "Q2 2026", 550, 28),
    _row("SV18 phase 1", "Silicon Valley", "Q2 2026", 2100, 260),
    _row("MI1 redevelopment", "Miami", "Q3 2026", 475, 59),
    _row("MT1 phase 3", "Montreal", "Q4 2026", 300, 37),
    _row("RJ3 phase 2", "Rio de Janeiro", "Q4 2026", 550, 46),
    _row("SP7 phase 1", "São Paulo", "Q4 2026", 600, 35),
    _row("SP4 phase 5", "São Paulo", "Q2 2027", 700, 74),
    _row("DC17 phases 1 and 2", "Washington, D.C.", "Q2 2027", 4700, 622),
    _row("DC22 phase 2", "Washington, D.C.", "Q2 2027", 2125, 144),
    _row("SV18 phase 2", "Silicon Valley", "Q2 2027", 850, 180),
    _row("TR6 phase 3", "Toronto", "Q3 2027", 1075, 123),
    _row("CH5 phase 2", "Chicago", "Q3 2027", 1625, 165),
    _row("DA12 phase 1", "Dallas", "Q2 2028", 3700, 837),
    _row("LG3 phase 1", "Lagos", "Q1 2026", 225, 22),
    _row("DX3 phase 2", "Dubai", "Q2 2026", 800, 81),
    _row("MD5 phase 1", "Madrid", "Q2 2026", 1650, 115),
    _row("IL3 phase 1", "Istanbul", "Q3 2026", 1325, 116),
    _row("FR8 phase 3", "Frankfurt", "Q4 2026", 1400, 107),
    _row("LD14 phase 1", "London", "Q1 2027", 1425, 242),
    _row("PA14 phase 1", "Paris", "Q2 2027", 675, 104),
    _row("LS2 phase 2", "Lisbon", "Q3 2027", 325, 31),
    _row("ZH4 phase 6", "Zurich", "Q3 2027", 200, 47),
    _row("LG4 phase 1", "Lagos", "Q4 2027", 975, 78),
    _row("DB10 phase 1", "Dublin", "Q1 2028", 475, 14),
    _row("LD14 phase 2", "London", "Q1 2028", 1425, 122),
    _row("FR12 phase 1", "Frankfurt", "Q2 2028", 1750, 381),
    _row("MU4 phase 3", "Munich", "Q2 2028", 1375, 342),
    _row("PA14 phase 2", "Paris", "Q2 2028", 600, 49),
    _row("FR15 phase 1", "Frankfurt", "Q3 2028", 1550, 487),
    _row("HK6 phase 1", "Hong Kong", "Q1 2026", 1000, 124),
    _row("OS3 phase 4", "Osaka", "Q1 2026", 550, 30),
    _row("JK1 phase 2", "Jakarta", "Q4 2026", 1125, 39),
    _row("SG6 phase 1", "Singapore", "Q1 2027", 1550, 290),
    _row("SY5 phase 4", "Sydney", "Q1 2027", 1350, 96),
    _row("KL2 phases 1 and 2", "Kuala Lumpur", "Q2 2027", 2200, 192),
    _row("MB3 phase 2", "Mumbai", "Q2 2027", 1375, 38),
    _row("BK1 phase 1", "Bangkok", "Q3 2027", 1175, 110),
    _row("JH2 phases 1 and 2", "Johor", "Q3 2027", 2225, 201),
    _row("CN1 phase 2", "Chennai", "Q4 2027", 1375, 88),
    _row("OS6 phase 1", "Osaka", "Q4 2028", 1850, 355),
]

SOURCE_SPECS: dict[str, dict[str, Any]] = {
    "curated-official-2026-07-20-equinix-ny11-new-york-phase-5.json": {
        "sha256": "7bd94a58c4fede51a67f9e4af52e31a010ea83456ff5eea4fcd8d5e5ec59fe7a",
        "campus_key": "curated:equinix-ny11-new-york-data-center",
        "campus_name": "Equinix NY11 New York Data Center",
        "project_key": "curated:equinix-ny11-new-york-data-center:phase-5",
        "project_name": "Equinix NY11 Phase 5",
        "country": "United States",
        "address": "New York metro, United States",
        "iso": ("US", "USA"),
    },
    "curated-official-2026-07-20-equinix-bg2-bogota-phase-2.json": {
        "sha256": "008d6b64aa0bd17935f2dad114f1f8ec2d4739398f548306dbf664f9bf7eedb8",
        "campus_key": "curated:equinix-bg2-bogota-data-center",
        "campus_name": "Equinix BG2 Bogotá Data Center",
        "project_key": "curated:equinix-bg2-bogota-data-center:phase-2",
        "project_name": "Equinix BG2 Phase 2",
        "country": "Colombia",
        "address": "Bogotá, Colombia",
        "iso": ("CO", "COL"),
    },
    "curated-official-2026-07-20-equinix-sv18-silicon-valley-phase-1.json": {
        "sha256": "108a3d955c3fcb15ccce637f8bb16970e7d87dfa7a3be2b63f7cdfcc4e418804",
        "campus_key": "curated:equinix-sv18-silicon-valley-data-center",
        "campus_name": "Equinix SV18 Silicon Valley Data Center",
        "project_key": "curated:equinix-sv18-silicon-valley-data-center:phase-1",
        "project_name": "Equinix SV18 Phase 1",
        "country": "United States",
        "address": "Silicon Valley, United States",
        "iso": ("US", "USA"),
    },
    "curated-official-2026-07-20-equinix-lg3-lagos-phase-1.json": {
        "sha256": "0d9809f941aab0d34084aa0b3595a1a593f5b02f749ef5a2ec1e7962e1df1e32",
        "campus_key": "curated:equinix-lg3-lagos-data-center",
        "campus_name": "Equinix LG3 Lagos Data Center",
        "project_key": "curated:equinix-lg3-lagos-data-center:phase-1",
        "project_name": "Equinix LG3 Phase 1",
        "country": "Nigeria",
        "address": "Lagos, Nigeria",
        "iso": ("NG", "NGA"),
    },
    "curated-official-2026-07-20-equinix-dx3-dubai-phase-2.json": {
        "sha256": "2af8962bea8be93e8f14739c464f4cc3b1df5d53716e2efef318a2424898c4b8",
        "campus_key": "curated:equinix-dx3-dubai-data-center",
        "campus_name": "Equinix DX3 Dubai Data Center",
        "project_key": "curated:equinix-dx3-dubai-data-center:phase-2",
        "project_name": "Equinix DX3 Phase 2",
        "country": "United Arab Emirates",
        "address": "Dubai, United Arab Emirates",
        "iso": ("AE", "ARE"),
    },
    "curated-official-2026-07-20-equinix-md5-madrid-phase-1.json": {
        "sha256": "19a4d9be83ed5448162886e856e0abdbe842d455b7715e872337e99ae1579609",
        "campus_key": "curated:equinix-md5-madrid-data-center",
        "campus_name": "Equinix MD5 Madrid Data Center",
        "project_key": "curated:equinix-md5-madrid-data-center:phase-1",
        "project_name": "Equinix MD5 Phase 1",
        "country": "Spain",
        "address": "Madrid, Spain",
        "iso": ("ES", "ESP"),
    },
    "curated-official-2026-07-20-equinix-hk6-hong-kong-phase-1.json": {
        "sha256": "f2a6f10b7138c9fa7dfc8c51402315ffa1aaf556d92b004159ee0c0970da7153",
        "campus_key": "curated:equinix-hk6-hong-kong-data-center",
        "campus_name": "Equinix HK6 Hong Kong Data Center",
        "project_key": "curated:equinix-hk6-hong-kong-data-center:phase-1",
        "project_name": "Equinix HK6 Phase 1",
        "country": "Hong Kong",
        "address": "Hong Kong",
        "iso": ("HK", "HKG"),
    },
    "curated-official-2026-07-20-equinix-os3-osaka-phase-4.json": {
        "sha256": "92de5f9fa26d00ab34118e2aeb6058426bd2db610bf89e88d9191c9c886ffffe",
        "campus_key": "curated:equinix-os3-osaka-data-center",
        "campus_name": "Equinix OS3 Osaka Data Center",
        "project_key": "curated:equinix-os3-osaka-data-center:phase-4",
        "project_name": "Equinix OS3 Phase 4",
        "country": "Japan",
        "address": "Osaka, Japan",
        "iso": ("JP", "JPN"),
    },
    "curated-official-2026-07-20-equinix-jk1-jakarta-phase-2.json": {
        "sha256": "f14cd026fab1eafca6675f107d9f7505ea0646a01baaa8c166fa91f9086d9a3f",
        "campus_key": "curated:equinix-jk1-jakarta-data-center",
        "campus_name": "Equinix JK1 Jakarta Data Center",
        "project_key": "curated:equinix-jk1-jakarta-data-center:phase-2",
        "project_name": "Equinix JK1 Phase 2",
        "country": "Indonesia",
        "address": "Jakarta, Indonesia",
        "iso": ("ID", "IDN"),
    },
    "curated-official-2026-07-20-equinix-sy5-sydney-phase-4.json": {
        "sha256": "2fb64fcf40db4dd6b84e3bbbd857edc0b16beb5dd7df0b73035d691bd6571bf1",
        "campus_key": "curated:equinix-sy5-sydney-data-center",
        "campus_name": "Equinix SY5 Sydney Data Center",
        "project_key": "curated:equinix-sy5-sydney-data-center:phase-4",
        "project_name": "Equinix SY5 Phase 4",
        "country": "Australia",
        "address": "Sydney, Australia",
        "iso": ("AU", "AUS"),
    },
    "curated-official-2026-07-20-equinix-kl2-kuala-lumpur-phases-1-2.json": {
        "sha256": "14cdba0d03f9bb2eb4f677eeba81b87a774df06a1da754e6bb5b1e568cc4e1f7",
        "campus_key": "curated:equinix-kl2-kuala-lumpur-data-center",
        "campus_name": "Equinix KL2 Kuala Lumpur Data Center",
        "project_key": "curated:equinix-kl2-kuala-lumpur-data-center:phases-1-and-2",
        "project_name": "Equinix KL2 Phases 1 and 2",
        "country": "Malaysia",
        "address": "Kuala Lumpur, Malaysia",
        "iso": ("MY", "MYS"),
    },
    "curated-official-2026-07-20-equinix-mb3-mumbai-phase-2.json": {
        "sha256": "5826774cb2b1e2202e8aab15ad037634f30a867533da16f1dd7a2f64f5a6c11f",
        "campus_key": "curated:equinix-mb3-mumbai-data-center",
        "campus_name": "Equinix MB3 Mumbai Data Center",
        "project_key": "curated:equinix-mb3-mumbai-data-center:phase-2",
        "project_name": "Equinix MB3 Phase 2",
        "country": "India",
        "address": "Mumbai, India",
        "iso": ("IN", "IND"),
    },
    "curated-official-2026-07-20-equinix-cn1-chennai-phase-2.json": {
        "sha256": "0eaacda3aa9cfb898d85e2dc9d13a69125685f1b87b6b2f7295a19eb4130ef20",
        "campus_key": "curated:equinix-cn1-chennai-data-center",
        "campus_name": "Equinix CN1 Chennai Data Center",
        "project_key": "curated:equinix-cn1-chennai-data-center:phase-2",
        "project_name": "Equinix CN1 Phase 2",
        "country": "India",
        "address": "Chennai, India",
        "iso": ("IN", "IND"),
    },
    "curated-official-2026-07-20-equinix-os6-osaka-phase-1.json": {
        "sha256": "528962021fa401ddb3d721d6a5a9bd0e53cfcc6ed7ac5b635fa854c7d86c48d2",
        "campus_key": "curated:equinix-os6-osaka-data-center",
        "campus_name": "Equinix OS6 Osaka Data Center",
        "project_key": "curated:equinix-os6-osaka-data-center:phase-1",
        "project_name": "Equinix OS6 Phase 1",
        "country": "Japan",
        "address": "Osaka, Japan",
        "iso": ("JP", "JPN"),
    },
}
SOURCES = tuple(SOURCE_SPECS)
NEW_CAMPUS_KEYS = {spec["campus_key"] for spec in SOURCE_SPECS.values()}
NEW_PROJECT_KEYS = {spec["project_key"] for spec in SOURCE_SPECS.values()}
NEW_ENTITY_KEYS = NEW_CAMPUS_KEYS | NEW_PROJECT_KEYS

AMERICAS_CORRECTED = (
    "curated-official-2026-07-20-equinix-mi1-miami-redevelopment.json",
    "curated-official-2026-07-20-equinix-mt1-montreal-phase-3.json",
    "curated-official-2026-07-20-equinix-dc17-washington-dc-phases-1-2.json",
    "curated-official-2026-07-20-equinix-dc22-washington-dc-phase-2.json",
    "curated-official-2026-07-20-equinix-sv18-silicon-valley-phase-2.json",
    "curated-official-2026-07-20-equinix-tr6-toronto-phase-3.json",
    "curated-official-2026-07-20-equinix-ch5-chicago-phase-2.json",
    "curated-official-2026-07-20-equinix-da12-dallas-phase-1.json",
)
EMEA_CORRECTED = (
    "curated-official-2026-07-20-equinix-il3-istanbul-phase-1.json",
    "curated-official-2026-07-20-equinix-fr8-frankfurt-phase-3.json",
    "curated-official-2026-07-20-equinix-ld14-london-phase-1.json",
    "curated-official-2026-07-20-equinix-pa14-paris-phase-1.json",
    "curated-official-2026-07-20-equinix-ls2-lisbon-phase-2.json",
    "curated-official-2026-07-20-equinix-zh4-zurich-phase-6.json",
    "curated-official-2026-07-20-equinix-db10-dublin-phase-1.json",
    "curated-official-2026-07-20-equinix-ld14-london-phase-2.json",
    "curated-official-2026-07-20-equinix-fr12-frankfurt-phase-1.json",
    "curated-official-2026-07-20-equinix-mu4-munich-phase-3.json",
    "curated-official-2026-07-20-equinix-pa14-paris-phase-2.json",
    "curated-official-2026-07-20-equinix-fr15-frankfurt-phase-1.json",
)
CORRECTED20 = AMERICAS_CORRECTED + EMEA_CORRECTED
FULL_CORRECTED_TABLE_SOURCES = CORRECTED20 + SOURCES
SV18_PHASE_1_SOURCE = (
    "curated-official-2026-07-20-equinix-sv18-silicon-valley-phase-1.json"
)
SV18_PHASE_2_SOURCE = (
    "curated-official-2026-07-20-equinix-sv18-silicon-valley-phase-2.json"
)
SV18_CAMPUS_KEY = "curated:equinix-sv18-silicon-valley-data-center"
SV18_EARLIER_RECORDED_AT = "2026-07-20T01:49:02Z"
SEMANTIC_TABLES = (
    "evidence",
    "entities",
    "campuses",
    "facilities",
    "buildings",
    "projects",
    "entity_snapshots",
    "lifecycle_observations",
    "operating_model_observations",
    "workload_observations",
    "capacity_estimates",
    "administrative_assignments",
)
TABLE_REPRESENTATIVES = (
    "curated-official-2026-07-19-equinix-sp7-sao-paulo-phase-1.json",
    "curated-official-2026-07-19-equinix-lg4-lagos-phase-1.json",
    AMERICAS_CORRECTED[0],
    EMEA_CORRECTED[0],
    SOURCES[0],
)
INTENTIONAL_ENTITY_REUSE = {
    "curated:equinix-sv18-silicon-valley-data-center": {
        "curated-official-2026-07-20-equinix-sv18-silicon-valley-phase-2.json"
    },
    "curated:equinix-hk6-hong-kong-data-center": {
        "curated-official-2026-07-20-equinix-hk6-current-opening.json"
    },
    "curated:equinix-hk6-hong-kong-data-center:phase-1": {
        "curated-official-2026-07-20-equinix-hk6-current-opening.json"
    },
    "curated:equinix-md5-madrid-data-center": {
        "curated-official-2026-07-20-equinix-md5-current-opening.json"
    },
    "curated:equinix-mb3-mumbai-data-center": {
        "curated-official-2026-07-20-equinix-mb3-current-opening.json"
    },
}


class EquinixRemainingFourteen10KTests(unittest.TestCase):
    def _load(self, name: str) -> dict[str, Any]:
        return json.loads((ROOT / "sources" / name).read_text(encoding="utf-8"))

    def _raw_evidence(self, name: str) -> bytes:
        raw = (ROOT / "sources" / name).read_bytes()
        start_marker = b'  "evidence": [\n'
        end_marker = b'\n  ],\n  "campus": {'
        start = raw.index(start_marker) + len(start_marker)
        end = raw.index(end_marker, start)
        return raw[start:end]

    def _offline(self) -> ExitStack:
        offline = AssertionError("curated source import attempted network access")
        stack = ExitStack()
        for target in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            stack.enter_context(patch.object(socket, target, side_effect=offline))
        return stack

    def _import(self, connection: Any, names: tuple[str, ...], repeat: int = 1) -> None:
        adapter = CuratedOfficialSourceAdapter()
        with self._offline():
            for _ in range(repeat):
                for name in names:
                    document = self._load(name)
                    adapter.import_file(
                        connection,
                        ROOT / "sources" / name,
                        retrieved_at=document["evidence"][0]["retrieved_at"],
                    )

    def _state(
        self, names: tuple[str, ...], repeat: int = 1
    ) -> tuple[
        tuple[str, tuple[str, ...], tuple[tuple[Any, ...], ...]], ...
    ]:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                self._import(connection, names, repeat)
                self.assertEqual(validate_database(connection), [])
                state = []
                for table in SEMANTIC_TABLES:
                    columns = tuple(
                        row["name"]
                        for row in connection.execute(f'PRAGMA table_info("{table}")')
                    )
                    projection = ", ".join(f'"{column}"' for column in columns)
                    rows = tuple(
                        tuple(row)
                        for row in connection.execute(
                            f'SELECT {projection} FROM "{table}" ORDER BY {projection}'
                        )
                    )
                    state.append((table, columns, rows))
                return tuple(state)
            finally:
                connection.close()

    def _state_rows(
        self,
        state: tuple[
            tuple[str, tuple[str, ...], tuple[tuple[Any, ...], ...]], ...
        ],
        table: str,
    ) -> list[dict[str, Any]]:
        matches = [entry for entry in state if entry[0] == table]
        self.assertEqual(len(matches), 1)
        _, columns, rows = matches[0]
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def _assert_document(self, name: str, document: dict[str, Any]) -> None:
        expected = SOURCE_SPECS[name]
        self.assertEqual(
            set(document),
            {
                "schema_version",
                "evidence",
                "campus",
                "project",
                "lifecycle",
                "operating_models",
                "workloads",
                "capacities",
            },
        )
        self.assertEqual(document["schema_version"], "1.0")
        self.assertEqual(len(document["evidence"]), 1)
        for kind in ("campus", "project"):
            entity = document[kind]
            self.assertEqual(
                set(entity),
                {
                    "stable_key",
                    "name",
                    "country",
                    "address",
                    "roles",
                    "coordinates",
                    "geometry",
                    "evidence_key",
                    "as_of_date",
                    "method",
                    "confidence",
                },
            )
            self.assertEqual(entity["country"], expected["country"])
            self.assertEqual(entity["address"], expected["address"])
            self.assertEqual(entity["roles"], {})
            self.assertIsNone(entity["coordinates"])
            self.assertIsNone(entity["geometry"])
            self.assertEqual(entity["evidence_key"], EVIDENCE_KEY)
            self.assertEqual(entity["as_of_date"], AS_OF_DATE)
            self.assertEqual(entity["method"], "authoritative_locality")
            self.assertEqual(entity["confidence"], 0.99)
        self.assertEqual(document["campus"]["stable_key"], expected["campus_key"])
        self.assertEqual(document["campus"]["name"], expected["campus_name"])
        self.assertEqual(document["project"]["stable_key"], expected["project_key"])
        self.assertEqual(document["project"]["name"], expected["project_name"])
        self.assertEqual(
            document["lifecycle"],
            [
                {
                    "entity": "project",
                    "value": "under_construction",
                    "evidence_key": EVIDENCE_KEY,
                    "as_of_date": AS_OF_DATE,
                    "method": "authoritative_physical_status_update",
                    "confidence": 0.99,
                }
            ],
        )
        self.assertEqual(document["operating_models"], [])
        self.assertEqual(document["workloads"], [])
        self.assertEqual(document["capacities"], [])
        non_evidence = {key: value for key, value in document.items() if key != "evidence"}
        serialized = json.dumps(non_evidence, sort_keys=True)
        for forbidden in (
            "target_open_quarter",
            "sellable_cabinets",
            "approximate_total_capex_usd_millions",
            "target_date",
            "pue",
            "megawatt",
            "energy",
        ):
            self.assertNotIn(forbidden, serialized.lower())

    def test_exact_hashes_canonical_json_shared_evidence_and_decoded_bogota(self) -> None:
        self.assertEqual(len(SOURCES), 14)
        self.assertEqual(len(NEW_CAMPUS_KEYS), 14)
        self.assertEqual(len(NEW_PROJECT_KEYS), 14)
        self.assertEqual(len(NEW_ENTITY_KEYS), 28)
        raw_evidence: list[bytes] = []
        evidence_objects: list[dict[str, Any]] = []
        for name, expected in SOURCE_SPECS.items():
            source = ROOT / "sources" / name
            self.assertTrue(source.is_file())
            self.assertFalse(source.is_symlink())
            self.assertEqual(
                hashlib.sha256(source.read_bytes()).hexdigest(), expected["sha256"]
            )
            document = self._load(name)
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                json.dumps(document, indent=2) + "\n",
            )
            self._assert_document(name, document)
            raw_evidence.append(self._raw_evidence(name))
            evidence_objects.append(document["evidence"][0])

        self.assertTrue(all(value == raw_evidence[0] for value in raw_evidence))
        self.assertTrue(all(value == evidence_objects[0] for value in evidence_objects))
        self.assertEqual(len(raw_evidence[0]), RAW_EVIDENCE_BYTES)
        self.assertEqual(
            hashlib.sha256(raw_evidence[0]).hexdigest(), RAW_EVIDENCE_SHA256
        )

        bg2 = self._load(
            "curated-official-2026-07-20-equinix-bg2-bogota-phase-2.json"
        )
        self.assertEqual(bg2["campus"]["name"], "Equinix BG2 Bogotá Data Center")
        self.assertEqual(bg2["campus"]["address"], "Bogotá, Colombia")
        self.assertEqual(bg2["project"]["address"], "Bogotá, Colombia")
        self.assertEqual(
            bg2["evidence"][0]["metadata"]["target_projects_as_reported"][1][
                "location"
            ],
            "Bogotá",
        )

    def test_capture_lineage_exact_rows_totals_and_guardrails(self) -> None:
        evidence = self._load(SOURCES[0])["evidence"][0]
        self.assertEqual(evidence["key"], EVIDENCE_KEY)
        self.assertEqual(evidence["kind"], "company_disclosure")
        self.assertEqual(
            evidence["title"], "Equinix 2025 Annual Report to Security Holders"
        )
        self.assertEqual(evidence["source_url"], PRIMARY_URL)
        self.assertEqual(evidence["publisher"], "Equinix, Inc.")
        self.assertEqual(evidence["source_family"], "equinix_sec_filings")
        self.assertEqual(evidence["published_at"], "2026-04-02")
        self.assertEqual(evidence["retrieved_at"], RETRIEVED_AT)
        self.assertEqual(evidence["content_hash"], BODY_SHA256)

        metadata = evidence["metadata"]
        self.assertIn(str(BODY_BYTES), metadata["content_hash_scope"])
        self.assertIn(str(HEADERS_BYTES), metadata["capture_headers_scope"])
        self.assertEqual(metadata["capture_headers_sha256"], HEADERS_SHA256)
        self.assertIn(str(WRITEOUT_BYTES), metadata["capture_curl_writeout_scope"])
        self.assertEqual(metadata["capture_curl_writeout_sha256"], WRITEOUT_SHA256)
        self.assertEqual(metadata["http_status"], 200)
        self.assertEqual(metadata["content_type"], "application/pdf")
        self.assertEqual(metadata["http_content_length_bytes_as_received"], BODY_BYTES)
        self.assertEqual(metadata["curl_size_download_bytes_as_received"], BODY_BYTES)
        self.assertEqual(metadata["response_http_date"], RETRIEVED_AT)
        self.assertEqual(metadata["form_type"], "ARS")
        self.assertEqual(metadata["ars_filing_accession"], "0001101239-26-000075")
        self.assertEqual(metadata["pdf_file_page_count"], 162)
        self.assertEqual(metadata["target_table_pdf_file_page"], 61)
        self.assertEqual(metadata["target_table_printed_page"], 44)
        self.assertEqual(metadata["construction_table_as_of_date"], AS_OF_DATE)
        self.assertEqual(metadata["target_projects_as_reported"], EXPECTED_NEW_ROWS)
        self.assertEqual(
            metadata["americas_complete_submission_evidence_key"],
            COMPLETE_SUBMISSION_EVIDENCE_KEY,
        )
        self.assertEqual(
            metadata["americas_complete_submission_body_sha256"],
            COMPLETE_SUBMISSION_BODY_SHA256,
        )
        self.assertEqual(metadata["inline_xbrl_html_body_bytes"], 4_071_886)
        self.assertEqual(
            metadata["inline_xbrl_html_body_sha256"], INLINE_XBRL_BODY_SHA256
        )
        self.assertEqual(
            metadata["prior_inline_xbrl_html_evidence_keys"],
            PRIOR_INLINE_XBRL_EVIDENCE_KEYS,
        )
        self.assertEqual(
            metadata["corroboration_group_id"], CORROBORATION_GROUP_ID
        )
        self.assertIs(metadata["independent_factual_corroboration"], False)
        self.assertIn(
            "same underlying Equinix 2025 Form 10-K construction table",
            metadata["source_artifact_distinction"],
        )
        self.assertIn(
            "not independent factual corroboration",
            metadata["source_artifact_distinction"],
        )
        self.assertEqual(metadata["full_table_reported_row_count"], 41)
        self.assertEqual(
            metadata["full_table_sellable_cabinets_total_as_reported"], 51_900
        )
        self.assertEqual(
            metadata["full_table_approximate_total_capex_usd_millions_as_reported"],
            6_549,
        )
        self.assertIn("historical status", metadata["historical_status_guardrail"])
        self.assertIn("does not prove", metadata["historical_status_guardrail"])
        self.assertIn("not an exact date", metadata["target_date_guardrail"])
        self.assertIn("not MW", metadata["cabinet_guardrail"])
        self.assertIn("not power", metadata["capex_guardrail"])
        self.assertIn("no capacity row", metadata["capacity_guardrail"])
        self.assertEqual(
            metadata["energy_guardrail"],
            "The filing supplies no project-specific PUE, energy, grid, "
            "generation, renewable-share, or measured-consumption observation "
            "for these fourteen rows.",
        )
        self.assertIn("fourteen rows", metadata["energy_guardrail"])
        self.assertNotIn("twelve rows", metadata["energy_guardrail"])
        self.assertIn("exactly one combined project", metadata["kl2_combined_row_guardrail"])
        self.assertIn("not evidence inputs", metadata["subsequent_event_guardrail"])
        self.assertIn("not normalized", metadata["role_guardrail"])
        self.assertIn("No satellite imagery", metadata["imagery_guardrail"])
        self.assertIn("QA metadata", metadata["table_total_guardrail"])

    def test_complete_41_row_table_closure_and_reported_section_math(self) -> None:
        rows: list[dict[str, Any]] = []
        for name in TABLE_REPRESENTATIVES:
            rows.extend(
                self._load(name)["evidence"][0]["metadata"][
                    "target_projects_as_reported"
                ]
            )
        self.assertEqual(len(rows), 41)
        by_property = {row["property"]: row for row in rows}
        expected = {row["property"]: row for row in EXPECTED_FULL_TABLE_ROWS}
        self.assertEqual(len(by_property), 41)
        self.assertEqual(by_property, expected)

        sections = {
            "Americas": EXPECTED_FULL_TABLE_ROWS[:14],
            "EMEA": EXPECTED_FULL_TABLE_ROWS[14:30],
            "Asia-Pacific": EXPECTED_FULL_TABLE_ROWS[30:],
        }
        expected_totals = {
            "Americas": (19_950, 2_648),
            "EMEA": (16_175, 2_338),
            "Asia-Pacific": (15_775, 1_563),
        }
        for section, section_rows in sections.items():
            actual = [by_property[row["property"]] for row in section_rows]
            self.assertEqual(actual, section_rows)
            self.assertEqual(
                (
                    sum(row["sellable_cabinets"] for row in actual),
                    sum(
                        row["approximate_total_capex_usd_millions"]
                        for row in actual
                    ),
                ),
                expected_totals[section],
            )
        self.assertEqual(
            sum(row["sellable_cabinets"] for row in rows), 51_900
        )
        self.assertEqual(
            sum(row["approximate_total_capex_usd_millions"] for row in rows),
            6_549,
        )

    def test_corrected20_delta_reverse_order_and_idempotence_are_exact(self) -> None:
        combined = CORRECTED20 + SOURCES
        self.assertEqual(
            self._state(combined),
            self._state(CORRECTED20 + tuple(reversed(SOURCES))),
        )
        self.assertEqual(self._state(SOURCES), self._state(tuple(reversed(SOURCES))))
        self.assertEqual(self._state(combined), self._state(combined, repeat=2))

        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                self._import(connection, CORRECTED20)
                before = {
                    (row["kind"], row["stable_key"])
                    for row in connection.execute("SELECT kind, stable_key FROM entities")
                }
                self.assertEqual(len(before), 38)
                self._import(connection, SOURCES)
                after = {
                    (row["kind"], row["stable_key"])
                    for row in connection.execute("SELECT kind, stable_key FROM entities")
                }
                delta = after - before
                self.assertEqual(
                    {key for kind, key in delta if kind == "campus"},
                    NEW_CAMPUS_KEYS
                    - {"curated:equinix-sv18-silicon-valley-data-center"},
                )
                self.assertEqual(
                    {key for kind, key in delta if kind == "project"},
                    NEW_PROJECT_KEYS,
                )
                self.assertEqual(len(delta), 27)
                counts = {
                    table: connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    for table in (
                        "entities",
                        "evidence",
                        "entity_snapshots",
                        "lifecycle_observations",
                        "operating_model_observations",
                        "workload_observations",
                        "capacity_estimates",
                    )
                }
                self.assertEqual(
                    counts,
                    {
                        "entities": 65,
                        "evidence": 3,
                        "entity_snapshots": 66,
                        "lifecycle_observations": 34,
                        "operating_model_observations": 0,
                        "workload_observations": 0,
                        "capacity_estimates": 0,
                    },
                )
                self.assertEqual(validate_database(connection), [])
            finally:
                connection.close()

    def test_full_corrected_table_import_is_transaction_order_invariant(self) -> None:
        release_builder_order = tuple(sorted(FULL_CORRECTED_TABLE_SOURCES))
        reverse_order = tuple(reversed(release_builder_order))
        old_first = CORRECTED20 + SOURCES
        new_first = SOURCES + CORRECTED20
        non_sv18 = tuple(
            name
            for name in release_builder_order
            if name not in {SV18_PHASE_1_SOURCE, SV18_PHASE_2_SOURCE}
        )
        repeated_interleaving = (
            SV18_PHASE_1_SOURCE,
            *non_sv18,
            SV18_PHASE_2_SOURCE,
            SV18_PHASE_1_SOURCE,
            SV18_PHASE_2_SOURCE,
        )
        orders = {
            "release-builder-sorted": release_builder_order,
            "full-reverse": reverse_order,
            "old-first": old_first,
            "new-first": new_first,
            "repeated-interleaving": repeated_interleaving,
        }

        states = {}
        for label, names in orders.items():
            with self.subTest(order=label):
                self.assertEqual(set(names), set(FULL_CORRECTED_TABLE_SOURCES))
                states[label] = self._state(names)

        expected_state = states["old-first"]
        for label, state in states.items():
            with self.subTest(equal_state=label):
                self.assertEqual(state, expected_state)

        entities = self._state_rows(expected_state, "entities")
        sv18_entity = [
            row for row in entities if row["stable_key"] == SV18_CAMPUS_KEY
        ]
        self.assertEqual(len(sv18_entity), 1)
        snapshots = [
            row
            for row in self._state_rows(expected_state, "entity_snapshots")
            if row["entity_id"] == sv18_entity[0]["id"]
            and row["as_of_date"] == AS_OF_DATE
        ]
        self.assertEqual(len(snapshots), 2)
        by_recorded_at = {row["recorded_at"]: row for row in snapshots}
        self.assertEqual(
            set(by_recorded_at),
            {SV18_EARLIER_RECORDED_AT, RETRIEVED_AT},
        )
        active = [row for row in snapshots if row["superseded_at"] is None]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["recorded_at"], RETRIEVED_AT)
        self.assertEqual(
            by_recorded_at[SV18_EARLIER_RECORDED_AT]["superseded_at"],
            RETRIEVED_AT,
        )

    def test_country_codes_and_historical_status_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection, _ = initialize(Path(temporary) / "atlas.sqlite")
            try:
                self._import(connection, SOURCES)
                features = export_geojson(
                    connection,
                    as_of=AS_OF_DATE,
                    recorded_at=RETRIEVED_AT,
                )["features"]
                self.assertEqual(len(features), 28)
                by_key = {
                    feature["properties"]["stable_key"]: feature["properties"]
                    for feature in features
                }
                for expected in SOURCE_SPECS.values():
                    for kind, key in (
                        ("campus", expected["campus_key"]),
                        ("project", expected["project_key"]),
                    ):
                        properties = by_key[key]
                        self.assertEqual(properties["entity_kind"], kind)
                        self.assertEqual(properties["country"], expected["country"])
                        self.assertEqual(
                            (
                                properties["country_iso_a2"],
                                properties["country_iso_a3"],
                            ),
                            expected["iso"],
                        )
                        self.assertEqual(
                            properties["source_country_tag"], expected["country"]
                        )
                        self.assertEqual(
                            properties["tags"]["address"], expected["address"]
                        )
                        if kind == "campus":
                            self.assertIsNone(properties["status"])
                        else:
                            self.assertEqual(properties["status"], "under_construction")
                            self.assertEqual(properties["status_as_of"], AS_OF_DATE)
                            self.assertEqual(
                                properties["status_method"],
                                "authoritative_physical_status_update",
                            )
                bg2 = by_key["curated:equinix-bg2-bogota-data-center"]
                self.assertEqual(bg2["name"], "Equinix BG2 Bogotá Data Center")
                self.assertEqual(bg2["tags"]["address"], "Bogotá, Colombia")
                self.assertEqual(
                    (bg2["country_iso_a2"], bg2["country_iso_a3"]),
                    ("CO", "COL"),
                )
            finally:
                connection.close()

    def test_global_collisions_are_only_explicit_temporal_identity_reuse(self) -> None:
        selected = {(ROOT / "sources" / name).resolve() for name in SOURCES}
        other_entity_keys: dict[str, set[str]] = {}
        other_evidence_keys: dict[str, set[str]] = {}
        ars_body_sources: set[str] = set()
        for source in sorted((ROOT / "sources").glob("curated-official*.json")):
            if source.resolve() in selected:
                continue
            document = json.loads(source.read_text(encoding="utf-8"))
            for kind in ("campus", "project"):
                entity = document.get(kind)
                if entity is not None:
                    other_entity_keys.setdefault(entity["stable_key"], set()).add(
                        source.name
                    )
            for evidence in document.get("evidence", []):
                other_evidence_keys.setdefault(evidence["key"], set()).add(
                    source.name
                )
                if evidence["content_hash"] == BODY_SHA256:
                    ars_body_sources.add(source.name)

        collisions = {
            key: other_entity_keys[key]
            for key in NEW_ENTITY_KEYS
            if key in other_entity_keys
        }
        self.assertEqual(collisions, INTENTIONAL_ENTITY_REUSE)
        self.assertNotIn(EVIDENCE_KEY, other_evidence_keys)
        self.assertEqual(ars_body_sources, set(EMEA_CORRECTED))

        source_by_entity = {
            expected[field]: self._load(name)[kind]
            for name, expected in SOURCE_SPECS.items()
            for kind, field in (("campus", "campus_key"), ("project", "project_key"))
        }
        for key, source_names in INTENTIONAL_ENTITY_REUSE.items():
            expected = source_by_entity[key]
            for source_name in source_names:
                document = self._load(source_name)
                matches = [
                    document[kind]
                    for kind in ("campus", "project")
                    if document.get(kind) is not None
                    and document[kind]["stable_key"] == key
                ]
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0]["name"], expected["name"])
                self.assertEqual(matches[0]["country"], expected["country"])

        sv18_phase_1 = self._load(
            "curated-official-2026-07-20-equinix-sv18-silicon-valley-phase-1.json"
        )
        sv18_phase_2 = self._load(
            "curated-official-2026-07-20-equinix-sv18-silicon-valley-phase-2.json"
        )
        for field in (
            "stable_key",
            "name",
            "country",
            "address",
            "roles",
            "coordinates",
            "geometry",
            "as_of_date",
            "method",
            "confidence",
        ):
            self.assertEqual(
                sv18_phase_1["campus"][field],
                sv18_phase_2["campus"][field],
            )
        self.assertNotEqual(
            sv18_phase_1["project"]["stable_key"],
            sv18_phase_2["project"]["stable_key"],
        )


if __name__ == "__main__":
    unittest.main()
