"""Scientific state and material-accounting primitives for enzyme activity v0."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any


def _non_negative(value: Any, *, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


@dataclass(frozen=True)
class Mixture:
    """A well-mixed liquid parcel in canonical uL, nmol, and logical seconds."""

    volume_ul: float = 0.0
    enzyme_nmol: float = 0.0
    substrate_nmol: float = 0.0
    product_nmol: float = 0.0
    lineage_ul: dict[str, float] = field(default_factory=dict)
    last_integrated_s: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "volume_ul",
            "enzyme_nmol",
            "substrate_nmol",
            "product_nmol",
            "last_integrated_s",
        ):
            object.__setattr__(self, name, _non_negative(getattr(self, name), name=name))
        lineage: dict[str, float] = {}
        for source_id, contribution_ul in self.lineage_ul.items():
            if type(source_id) is not str or not source_id or source_id.strip() != source_id:
                raise ValueError("lineage source IDs must be non-empty trimmed strings")
            amount = _non_negative(contribution_ul, name=f"lineage_ul.{source_id}")
            if amount > 0:
                lineage[source_id] = amount
        if self.volume_ul == 0 and any(
            value > 0
            for value in (self.enzyme_nmol, self.substrate_nmol, self.product_nmol)
        ):
            raise ValueError("a zero-volume mixture cannot contain material")
        if not math.isclose(
            sum(lineage.values()), self.volume_ul, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError("lineage contributions must sum to mixture volume")
        object.__setattr__(self, "lineage_ul", lineage)

    @classmethod
    def pure(
        cls,
        *,
        source_id: str,
        volume_ul: float,
        enzyme_concentration_mM: float = 0.0,
        substrate_concentration_mM: float = 0.0,
        product_concentration_mM: float = 0.0,
        at_s: float = 0.0,
    ) -> Mixture:
        volume = _non_negative(volume_ul, name="volume_ul")
        return cls(
            volume_ul=volume,
            enzyme_nmol=volume
            * _non_negative(enzyme_concentration_mM, name="enzyme_concentration_mM"),
            substrate_nmol=volume
            * _non_negative(substrate_concentration_mM, name="substrate_concentration_mM"),
            product_nmol=volume
            * _non_negative(product_concentration_mM, name="product_concentration_mM"),
            lineage_ul={} if volume == 0 else {source_id: volume},
            last_integrated_s=at_s,
        )

    def concentration_mM(self, component: str) -> float:
        if component not in {"enzyme", "substrate", "product"}:
            raise ValueError(f"unknown component {component!r}")
        if self.volume_ul == 0:
            return 0.0
        return getattr(self, f"{component}_nmol") / self.volume_ul

    def withdraw(self, volume_ul: float) -> tuple[Mixture, Mixture]:
        volume = _non_negative(volume_ul, name="withdraw.volume_ul")
        if volume <= 0 or volume > self.volume_ul:
            raise ValueError("withdraw volume must be positive and no greater than available volume")
        fraction = volume / self.volume_ul
        remainder_fraction = 1.0 - fraction

        def scaled_lineage(scale: float) -> dict[str, float]:
            return {
                source_id: contribution * scale
                for source_id, contribution in self.lineage_ul.items()
                if contribution * scale > 0
            }

        aliquot = Mixture(
            volume_ul=volume,
            enzyme_nmol=self.enzyme_nmol * fraction,
            substrate_nmol=self.substrate_nmol * fraction,
            product_nmol=self.product_nmol * fraction,
            lineage_ul=scaled_lineage(fraction),
            last_integrated_s=self.last_integrated_s,
        )
        if remainder_fraction == 0:
            remainder = Mixture(last_integrated_s=self.last_integrated_s)
        else:
            remainder = Mixture(
                volume_ul=self.volume_ul - volume,
                enzyme_nmol=self.enzyme_nmol * remainder_fraction,
                substrate_nmol=self.substrate_nmol * remainder_fraction,
                product_nmol=self.product_nmol * remainder_fraction,
                lineage_ul=scaled_lineage(remainder_fraction),
                last_integrated_s=self.last_integrated_s,
            )
        return remainder, aliquot

    def combine(self, other: Mixture) -> Mixture:
        if not math.isclose(
            self.last_integrated_s,
            other.last_integrated_s,
            rel_tol=0,
            abs_tol=1e-12,
        ):
            raise ValueError("mixtures must be integrated to the same logical time before combining")
        lineage = dict(self.lineage_ul)
        for source_id, contribution in other.lineage_ul.items():
            lineage[source_id] = lineage.get(source_id, 0.0) + contribution
        return Mixture(
            volume_ul=self.volume_ul + other.volume_ul,
            enzyme_nmol=self.enzyme_nmol + other.enzyme_nmol,
            substrate_nmol=self.substrate_nmol + other.substrate_nmol,
            product_nmol=self.product_nmol + other.product_nmol,
            lineage_ul=lineage,
            last_integrated_s=self.last_integrated_s,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "volume_ul": self.volume_ul,
            "enzyme_nmol": self.enzyme_nmol,
            "substrate_nmol": self.substrate_nmol,
            "product_nmol": self.product_nmol,
            "lineage_ul": dict(sorted(self.lineage_ul.items())),
            "last_integrated_s": self.last_integrated_s,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Mixture:
        return cls(**value)


@dataclass
class ExperimentState:
    """Minimal mutable container whose time advances every liquid parcel."""

    clock_s: float
    reaction_parameters: Any
    wells: dict[str, Mixture] = field(default_factory=dict)
    tip: Mixture = field(default_factory=Mixture)

    def __post_init__(self) -> None:
        self.clock_s = _non_negative(self.clock_s, name="clock_s")
        for location, mixture in self.wells.items():
            if not location:
                raise ValueError("well location must be non-empty")
            if mixture.last_integrated_s != self.clock_s:
                raise ValueError("all mixtures must start at the experiment clock")
        if self.tip.last_integrated_s != self.clock_s:
            raise ValueError("tip mixture must start at the experiment clock")

    def advance_to(self, target_s: float) -> None:
        from .chemistry import advance_reaction

        target = _non_negative(target_s, name="target_s")
        if target < self.clock_s:
            raise ValueError("logical experiment time cannot move backward")
        self.wells = {
            location: advance_reaction(mixture, target, self.reaction_parameters)
            for location, mixture in self.wells.items()
        }
        self.tip = advance_reaction(self.tip, target, self.reaction_parameters)
        self.clock_s = target

    def wait(self, duration_s: float) -> None:
        duration = _non_negative(duration_s, name="duration_s")
        self.advance_to(self.clock_s + duration)

    def transfer(self, source: str, destination: str, volume_ul: float) -> None:
        if source == destination:
            raise ValueError("source and destination must differ")
        if source not in self.wells:
            raise ValueError(f"unknown source well {source!r}")
        destination_mixture = self.wells.get(
            destination, Mixture(last_integrated_s=self.clock_s)
        )
        remainder, aliquot = self.wells[source].withdraw(volume_ul)
        self.wells[source] = remainder
        self.wells[destination] = destination_mixture.combine(aliquot)

    def aspirate(self, source: str, volume_ul: float) -> None:
        if self.tip.volume_ul != 0:
            raise ValueError("v0 requires an empty tip before aspiration")
        remainder, aliquot = self.wells[source].withdraw(volume_ul)
        self.wells[source] = remainder
        self.tip = aliquot

    def dispense(self, destination: str, volume_ul: float) -> None:
        remainder, aliquot = self.tip.withdraw(volume_ul)
        destination_mixture = self.wells.get(
            destination, Mixture(last_integrated_s=self.clock_s)
        )
        self.tip = remainder
        self.wells[destination] = destination_mixture.combine(aliquot)

    def clone_mixture(self, location: str) -> Mixture:
        return replace(self.wells[location], lineage_ul=dict(self.wells[location].lineage_ul))
