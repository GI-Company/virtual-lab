"""
virtual_lab.domain.compatibility
─────────────────────────────────
Compatibility checking for Compare workspace.

Two observations are scientifically comparable only if ALL THREE hold:
  1. Semantic quantity identity — semantic_name must match
  2. Compatible physical dimension — PhysicalDimension must match
  3. Convertible units — both units must be registered in the same dimension scale map

Physical dimension alone is insufficient.
Example: MAGNETIC_FLUX_DENSITY matches between Bx and By by dimension, but
semantic_name "magnetic_flux_density_x" ≠ "magnetic_flux_density_y", so they
are NOT comparable to each other — only to the same component in a different run.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Tuple

from virtual_lab.domain.observation import ExperimentObservation, QuantityDescriptor


@dataclass(frozen=True)
class CompatiblePair:
    quantity_a: QuantityDescriptor
    quantity_b: QuantityDescriptor
    observation_a: ExperimentObservation
    observation_b: ExperimentObservation


@dataclass(frozen=True)
class IncompatiblePair:
    quantity_a: QuantityDescriptor
    observation_a: ExperimentObservation
    reason: str


def find_compatible_pairs(
    observations_a: List[ExperimentObservation],
    observations_b: List[ExperimentObservation],
) -> Tuple[List[CompatiblePair], List[IncompatiblePair]]:
    """
    Partition all quantities in observations_a against observations_b into
    comparable and incomparable sets.

    Returns:
        (compatible_pairs, incompatible_quantities_from_a)
    """
    compatible: List[CompatiblePair] = []
    incompatible: List[IncompatiblePair] = []

    for obs_a in observations_a:
        for qty_a in obs_a.quantities:
            matched = False
            for obs_b in observations_b:
                for qty_b in obs_b.quantities:
                    if qty_a.is_comparable_to(qty_b):
                        compatible.append(
                            CompatiblePair(qty_a, qty_b, obs_a, obs_b)
                        )
                        matched = True
                        break
                if matched:
                    break

            if not matched:
                # Build a useful reason
                same_dim_found = any(
                    qty_b.physical_dimension == qty_a.physical_dimension
                    for obs_b in observations_b
                    for qty_b in obs_b.quantities
                )
                if same_dim_found:
                    reason = (
                        f"No matching semantic_name '{qty_a.semantic_name}' "
                        f"in experiment B (dimension {qty_a.physical_dimension.value} present "
                        f"but different quantity)"
                    )
                else:
                    reason = (
                        f"No observation in experiment B has dimension "
                        f"{qty_a.physical_dimension.value}"
                    )
                incompatible.append(
                    IncompatiblePair(qty_a, obs_a, reason)
                )

    return compatible, incompatible
