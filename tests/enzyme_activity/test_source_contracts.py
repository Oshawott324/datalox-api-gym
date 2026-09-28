from __future__ import annotations

import asyncio
import inspect
import json
from importlib.metadata import version
from pathlib import Path

import pytest
from pylabrobot.plate_reading import PlateReader
from pylabrobot.plate_reading.backend import PlateReaderBackend
from pylabrobot.resources import Cor_96_wellplate_360ul_Fb

from api_gym.instrument_models.plate_reader_v0.pylabrobot_backend import (
    AuthoredAbsorbanceBackend,
)
from api_gym.worlds.enzyme_activity_v0.defaults import (
    ANALYSIS_RULES,
    FINAL_SUBSTRATE_CONCENTRATION_MM,
    REACTION_PARAMETERS,
    READER_PROFILE,
    SUBSTRATE_STOCK_CONCENTRATION_MM,
    UNDILUTED_SAMPLE_FRACTION,
)
from api_gym.worlds.enzyme_activity_v0.verifier import VerificationRules


ROOT = Path(__file__).parents[2] / "worlds" / "enzyme_activity_v0"


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_contract_slice_is_complete_and_every_assay_number_has_a_basis() -> None:
    required = {
        "source_refs.json",
        "sources.lock.json",
        "contracts/assay_sop.json",
        "contracts/reader_profile.json",
        "contracts/model_assumptions.json",
    }
    assert required <= {
        path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*.json")
    }
    sop = load_json("contracts/assay_sop.json")
    refs = {item["id"] for item in load_json("source_refs.json")["sources"]}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            if "value" in value:
                assert value["basis"] in {
                    "published_method",
                    "native_software_observation",
                    "provisional_authored_model",
                }
                assert value["evidence_ref"] in refs
                if value["basis"] == "provisional_authored_model":
                    assert value["rationale"]
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(sop)
    assert sop["signal"]["wavelength"]["value"] == 405
    assert sop["permitted_reporting_units"] == ["delta_absorbance_per_minute"]


def test_json_contract_and_executable_defaults_are_identical() -> None:
    sop = load_json("contracts/assay_sop.json")
    reader = load_json("contracts/reader_profile.json")
    model = load_json("contracts/model_assumptions.json")
    supported = reader["supported_settings"]
    authored = reader["authored_parameters"]
    assert READER_PROFILE.to_dict() == {
        "profile_id": reader["profile_id"],
        "wavelength_nm": supported["wavelength_nm"],
        "temperature_c": supported["temperature_c"],
        "compatible_plate_load_name": supported["compatible_plate_load_name"],
        "reaction_volume_interval_ul": [
            supported["reaction_volume_min_ul"],
            supported["reaction_volume_max_ul"],
        ],
        "optical_path_cm": authored["optical_path_cm"],
        "product_extinction_per_mM_cm": authored["product_extinction_per_mM_cm"],
        "blank_intercept_abs": authored["blank_intercept_abs"],
        "blank_drift_abs_per_s": authored["blank_drift_abs_per_s"],
        "noise_sd_abs": authored["noise_sd_abs"],
        "detector_interval_abs": [
            authored["detector_min_abs"],
            authored["detector_max_abs"],
        ],
        "per_well_delay_s": authored["per_well_delay_s"],
        "evidence_level": "provisional_authored_model",
    }
    assert REACTION_PARAMETERS.kcat_per_s == model["reaction"]["kcat_per_s"]
    assert REACTION_PARAMETERS.km_mM == model["reaction"]["Km_mM"]
    assert (
        ANALYSIS_RULES.minimum_observations
        == sop["fit"]["minimum_observations"]["value"]
    )
    assert ANALYSIS_RULES.minimum_window_s == sop["fit"]["minimum_window"]["value"]
    assert (
        FINAL_SUBSTRATE_CONCENTRATION_MM
        == sop["fixed_conditions"]["final_substrate_concentration"]["value"]
    )
    assert (
        SUBSTRATE_STOCK_CONCENTRATION_MM
        == sop["fixed_conditions"]["substrate_stock_concentration"]["value"]
    )
    assert (
        UNDILUTED_SAMPLE_FRACTION
        == sop["sample_dilution"]["undiluted_sample_fraction"]["value"]
    )
    verification = VerificationRules()
    assert (
        verification.reference_rate_min
        == sop["controls"]["reference_rate_interval"]["minimum"]["value"]
    )
    assert (
        verification.reference_rate_max
        == sop["controls"]["reference_rate_interval"]["maximum"]["value"]
    )
    assert (
        verification.maximum_relative_uncertainty
        == sop["fit"]["maximum_relative_standard_error"]["value"]
    )
    assert (
        verification.numeric_relative_tolerance
        == sop["report_comparison"]["relative_tolerance"]["value"]
    )
    assert (
        verification.numeric_absolute_tolerance
        == sop["report_comparison"]["absolute_tolerance"]["value"]
    )


def test_pinned_reader_interface_signatures_match_the_audited_contract() -> None:
    assert version("pylabrobot") == "0.2.1"
    assert str(inspect.signature(PlateReader.read_absorbance)) == (
        "(self, wavelength: int, wells: Optional[List[pylabrobot.resources.well.Well]] "
        "= None, use_new_return_type: bool = False, **backend_kwargs) -> List[Dict]"
    )
    assert str(inspect.signature(PlateReaderBackend.read_absorbance)) == (
        "(self, plate: 'Plate', wells: 'List[Well]', wavelength: 'int') -> 'List[Dict]'"
    )


def test_authored_backend_uses_native_structured_and_legacy_shapes() -> None:
    async def exercise() -> tuple[list[dict], list[list[float | None]]]:
        matrix = [[0.0 for _ in range(12)] for _ in range(8)]
        matrix[0][0] = 0.123
        matrix[0][1] = None
        backend = AuthoredAbsorbanceBackend(
            lambda plate, wells, wavelength: matrix,
            logical_time_s=12.5,
            temperature_c=37.0,
        )
        reader = PlateReader(
            name="authored-reader",
            size_x=0,
            size_y=0,
            size_z=0,
            backend=backend,
        )
        reader.assign_child_resource(Cor_96_wellplate_360ul_Fb(name="assay-plate"))
        await reader.setup()
        structured = await reader.read_absorbance(405, use_new_return_type=True)
        legacy = await reader.read_absorbance(405)
        await reader.stop()
        return structured, legacy

    structured, legacy = asyncio.run(exercise())
    assert structured == [
        {
            "wavelength": 405,
            "time": 12.5,
            "temperature": 37.0,
            "data": legacy,
        }
    ]
    assert legacy[0][:2] == [0.123, None]


def test_authored_backend_rejects_an_invalid_native_cell_shape() -> None:
    async def exercise() -> None:
        backend = AuthoredAbsorbanceBackend(
            lambda plate, wells, wavelength: [[float("nan")]]
        )
        reader = PlateReader(
            name="authored-reader",
            size_x=0,
            size_y=0,
            size_z=0,
            backend=backend,
        )
        reader.assign_child_resource(Cor_96_wellplate_360ul_Fb(name="assay-plate"))
        await reader.setup()
        with pytest.raises(ValueError, match="finite numbers or null"):
            await reader.read_absorbance(405, use_new_return_type=True)
        await reader.stop()

    asyncio.run(exercise())
