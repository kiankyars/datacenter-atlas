"""Workspace import shim for the nested installable package.

This keeps ``python -m datacenter_atlas`` and repository-root unittest discovery working without an
editable install, while the inner package remains directly installable from this directory.
"""

from __future__ import annotations

import importlib
from pathlib import Path
import sys

from .datacenter_atlas import *  # noqa: F401,F403
from .datacenter_atlas import __all__, __version__


_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.append(_project_root)


for _module_name in (
    "adapters",
    "blind_tile_frame",
    "blind_tile_auxiliary_integration",
    "brazil_pncp_publications",
    "candidate_fusion",
    "chile_sea_pertinence",
    "cli",
    "cleanview_assessment",
    "construction_master",
    "construction_master_v2",
    "construction_map",
    "construction_map_v2",
    "coverage_audit",
    "curated",
    "cross_release",
    "current_coverage",
    "database",
    "denmark_plandata_local_plans",
    "edgemode_assessment",
    "england_planning_data",
    "epbc_referrals",
    "epa_echo_frs_assessment",
    "epoch",
    "epoch_source_capture",
    "exact_identity_decisions",
    "federated_release",
    "finland_lvv_environmental_permits",
    "france_igedd_ae",
    "fuzzy_shortlist",
    "fuzzy_snapshot",
    "germany_uvp_verbund",
    "global_snapshot",
    "gdelt",
    "iaac_registry",
    "india_parivesh_environmental_clearances",
    "ireland_planning",
    "italy_mase_via_vas",
    "japan_moe_casebook",
    "loudoun_data_center_assessment",
    "malaysia_kpkt_osc3plus",
    "models",
    "microsoft_building_footprints",
    "natural_earth",
    "netherlands_koop",
    "new_zealand_fast_track",
    "nsw_major_projects",
    "ohsome",
    "osm",
    "osm_blind_tile_auxiliary",
    "osm_blind_tile_auxiliary_v2",
    "osm_blind_tile_auxiliary_v3",
    "osm_construction",
    "osm_fuzzy",
    "osm_planet",
    "open_buildings_temporal",
    "open_seed_release",
    "overture",
    "peeringdb_assessment",
    "pjm_large_load_assessment",
    "poland_gdos_sios_ekoportal",
    "pnnl",
    "pwc_build_out_assessment",
    "publication_release",
    "release",
    "release_contract_v4",
    "repository",
    "resolution",
    "satellite_batch",
    "satellite_batch_recovery",
    "satellite_calibration",
    "satellite_calibration_aggregate",
    "satellite_calibration_blind_rereview",
    "satellite_calibration_rereview",
    "satellite_calibration_rerun",
    "satellite_catalog",
    "satellite_catalog_reselection",
    "satellite_change",
    "satellite_change_batch",
    "satellite_change_mosaic",
    "satellite_mosaic_preparation",
    "satellite_mosaic_preparation_v3",
    "satellite_mosaic_preparation_v4",
    "satellite_mosaic_preparation_v5",
    "satellite_mosaic_preparation_v6",
    "satellite_reselected_change_batch",
    "satellite_queue",
    "scrutica",
    "scrutica_snapshot",
    "service",
    "singapore_bca_green_mark",
    "singapore_ura_planning_decisions",
    "spain_boe",
    "south_korea_eiass_nier",
    "taginfo_targets",
    "thailand_onep_smart_eia",
    "timestamps",
    "uva",
    "virginia_deq_air_permits",
    "wikidata",
    "within_release_resolution",
):
    _module = importlib.import_module(f".datacenter_atlas.{_module_name}", __name__)
    sys.modules[f"{__name__}.{_module_name}"] = _module
    setattr(sys.modules[__name__], _module_name, _module)
