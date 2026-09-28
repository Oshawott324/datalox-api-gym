"""Single executable definition of the admitted v0 numeric contract."""

from api_gym.instrument_models.plate_reader_v0.contracts import ReaderProfile

from .analysis import AnalysisRules
from .chemistry import ReactionParameters


REACTION_PARAMETERS = ReactionParameters(kcat_per_s=0.08, km_mM=0.25)

READER_PROFILE = ReaderProfile(
    profile_id="pylabrobot_0_2_1_authored_absorbance_405_v0",
    wavelength_nm=405,
    temperature_c=37,
    compatible_plate_load_name="corning_96_wellplate_360ul_flat",
    reaction_volume_min_ul=80,
    reaction_volume_max_ul=200,
    optical_path_cm=0.5,
    product_extinction_per_mM_cm=18.5,
    blank_intercept_abs=0.04,
    blank_drift_abs_per_s=0.00001,
    noise_sd_abs=0.002,
    detector_min_abs=0,
    detector_max_abs=2,
    per_well_delay_s=0.2,
)

ANALYSIS_RULES = AnalysisRules(
    minimum_observations=4,
    minimum_window_s=90,
    usable_absorbance_min=0.02,
    usable_absorbance_max=1.5,
)

__all__ = ["ANALYSIS_RULES", "REACTION_PARAMETERS", "READER_PROFILE"]
