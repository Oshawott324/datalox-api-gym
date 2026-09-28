"""Bounded Michaelis--Menten dynamics with explicit dimensional units."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from scipy.integrate import solve_ivp

from .state import Mixture


@dataclass(frozen=True)
class ReactionParameters:
    kcat_per_s: float
    km_mM: float
    solver_method: str = "DOP853"
    relative_tolerance: float = 1e-9
    absolute_tolerance_nmol: float = 1e-12

    def __post_init__(self) -> None:
        for name in (
            "kcat_per_s",
            "km_mM",
            "relative_tolerance",
            "absolute_tolerance_nmol",
        ):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, float(value))
        if self.kcat_per_s < 0 or self.km_mM <= 0:
            raise ValueError("kcat must be non-negative and Km must be positive")
        if self.relative_tolerance <= 0 or self.absolute_tolerance_nmol <= 0:
            raise ValueError("solver tolerances must be positive")
        if self.solver_method != "DOP853":
            raise ValueError("enzyme activity v0 freezes the DOP853 solver")


def instantaneous_rate_nmol_s(
    mixture: Mixture, parameters: ReactionParameters
) -> float:
    if mixture.volume_ul == 0 or mixture.enzyme_nmol == 0 or mixture.substrate_nmol == 0:
        return 0.0
    substrate_mM = mixture.substrate_nmol / mixture.volume_ul
    return (
        parameters.kcat_per_s
        * mixture.enzyme_nmol
        * substrate_mM
        / (parameters.km_mM + substrate_mM)
    )


def advance_reaction(
    mixture: Mixture,
    target_s: float,
    parameters: ReactionParameters,
) -> Mixture:
    if type(target_s) not in (int, float) or not math.isfinite(float(target_s)):
        raise ValueError("target_s must be finite")
    target = float(target_s)
    if target < mixture.last_integrated_s:
        raise ValueError("reaction time cannot move backward")
    if target == mixture.last_integrated_s:
        return mixture
    if (
        mixture.volume_ul == 0
        or mixture.enzyme_nmol == 0
        or mixture.substrate_nmol == 0
        or parameters.kcat_per_s == 0
    ):
        return Mixture(**{**mixture.to_dict(), "last_integrated_s": target})

    initial_substrate = mixture.substrate_nmol
    conserved_reactive = mixture.substrate_nmol + mixture.product_nmol

    def derivative(_time_s: float, amount: Any) -> list[float]:
        substrate_nmol = float(amount[0])
        if substrate_nmol < 0:
            raise RuntimeError("kinetics solver evaluated a negative substrate amount")
        substrate_mM = substrate_nmol / mixture.volume_ul
        rate = (
            parameters.kcat_per_s
            * mixture.enzyme_nmol
            * substrate_mM
            / (parameters.km_mM + substrate_mM)
        )
        return [-rate]

    def exhausted(_time_s: float, amount: Any) -> float:
        return float(amount[0])

    exhausted.terminal = True  # type: ignore[attr-defined]
    exhausted.direction = -1  # type: ignore[attr-defined]
    result = solve_ivp(
        derivative,
        (mixture.last_integrated_s, target),
        [initial_substrate],
        method=parameters.solver_method,
        rtol=parameters.relative_tolerance,
        atol=parameters.absolute_tolerance_nmol,
        events=exhausted,
    )
    if not result.success:
        raise RuntimeError(f"kinetics integration failed: {result.message}")
    event_reached = bool(result.t_events and len(result.t_events[0]))
    substrate = 0.0 if event_reached else float(result.y[0, -1])
    if substrate < -parameters.absolute_tolerance_nmol:
        raise RuntimeError("kinetics integration violated non-negative substrate")
    if substrate < 0:
        raise RuntimeError("kinetics integration returned negative substrate without exhaustion")
    if substrate > initial_substrate + parameters.absolute_tolerance_nmol:
        raise RuntimeError("kinetics integration created substrate")
    product = conserved_reactive - substrate
    if not math.isclose(
        substrate + product,
        conserved_reactive,
        rel_tol=0,
        abs_tol=parameters.absolute_tolerance_nmol,
    ):
        raise RuntimeError("kinetics integration violated material conservation")
    return Mixture(
        volume_ul=mixture.volume_ul,
        enzyme_nmol=mixture.enzyme_nmol,
        substrate_nmol=substrate,
        product_nmol=product,
        lineage_ul=dict(mixture.lineage_ul),
        last_integrated_s=target,
    )


def integrated_time_s(
    *,
    initial_substrate_mM: float,
    final_substrate_mM: float,
    volume_ul: float,
    enzyme_nmol: float,
    parameters: ReactionParameters,
) -> float:
    """Closed-form elapsed time for an independent numerical test oracle."""

    if not 0 < final_substrate_mM <= initial_substrate_mM:
        raise ValueError("closed-form concentrations must satisfy 0 < final <= initial")
    if volume_ul <= 0 or enzyme_nmol <= 0 or parameters.kcat_per_s <= 0:
        raise ValueError("closed-form material and kcat values must be positive")
    return volume_ul / (parameters.kcat_per_s * enzyme_nmol) * (
        initial_substrate_mM
        - final_substrate_mM
        + parameters.km_mM
        * math.log(initial_substrate_mM / final_substrate_mM)
    )
