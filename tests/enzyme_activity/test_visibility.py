from __future__ import annotations

from api_gym.instrument_models.plate_reader_v0.contracts import (
    AcquisitionSettings,
    ReaderProfile,
)
from api_gym.instrument_models.plate_reader_v0.dynamics import PlateReaderDynamics
from api_gym.worlds.enzyme_activity_v0.observations import public_experiment_observation
from api_gym.worlds.enzyme_activity_v0.state import Mixture


def test_future_readings_and_latent_model_parameters_are_not_observable() -> None:
    profile = ReaderProfile(
        "visibility-profile",
        405,
        37,
        "corning_96_wellplate_360ul_flat",
        80,
        200,
        0.5,
        18.5,
        0.04,
        0.00001,
        0,
        0,
        2,
        0.2,
    )
    reader = PlateReaderDynamics(profile, noise_seed=9)
    job_id = reader.start_series(
        plate_id="plate-public",
        plate_revision=2,
        start_s=0,
        settings=AcquisitionSettings(405, 37, ("A1",), (0, 60, 120)),
    )
    mixture = Mixture.pure(source_id="public-sample", volume_ul=100)
    reader.acquire_due(job_id, now_s=0, mixture_at=lambda well, at_s: mixture)
    observation = public_experiment_observation(
        logical_time_s=0,
        inventory={"sample_labels": ["SAMPLE-A"]},
        plate_id="plate-public",
        plate_revision=2,
        plate_location="reader",
        reader_jobs=(reader.get_job(job_id),),
    )
    text = repr(observation)
    assert len(observation["reader_jobs"][0]["measurements"]) == 1
    for forbidden in (
        "kcat",
        "km_mM",
        "noise_seed",
        "scheduled_at_s",
        "enzyme_nmol",
        "substrate_nmol",
    ):
        assert forbidden not in text
