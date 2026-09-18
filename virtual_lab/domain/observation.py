"""
virtual_lab.domain.observation
──────────────────────────────
Scientific observation types used across VirtualLab workspaces.

Key design decisions
────────────────────
• QuantityDescriptor carries full semantic identity (name + dimension + canonical units)
  so that the Compare workspace can determine compatibility without knowing whether an
  observation came from a phone sensor, a bench instrument, or a simulation.

• Vector component identity is preserved explicitly:
    Bx, By, Bz each get their own QuantityDescriptor with component_axis set.
    The derived magnitude |B| carries EpistemicState.DERIVED and no component_axis.

• No Android transport DTOs appear here (CameraStreamKey, AdbReverseRunner, etc.).
  The Instruments layer maps protocol artifacts → ExperimentObservation via assemblers.py.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from virtual_lab.domain.epistemics import EpistemicState


# ─────────────────────────────────────────────────────────────────────────────
# Physical Dimension Registry
# A controlled vocabulary of physical dimensions.
# Compatibility checking uses this, not raw units strings.
# ─────────────────────────────────────────────────────────────────────────────

class PhysicalDimension(Enum):
    """Controlled vocabulary of physical dimensions used in VirtualLab."""
    MAGNETIC_FLUX_DENSITY   = "MAGNETIC_FLUX_DENSITY"    # T, uT, mT
    ACCELERATION            = "ACCELERATION"              # m/s^2, g
    ANGULAR_VELOCITY        = "ANGULAR_VELOCITY"          # rad/s, deg/s
    ILLUMINANCE             = "ILLUMINANCE"               # lx
    PRESSURE                = "PRESSURE"                  # hPa, Pa, atm
    TEMPERATURE             = "TEMPERATURE"               # K, °C
    VOLTAGE                 = "VOLTAGE"                   # V, mV
    CURRENT                 = "CURRENT"                   # A, mA
    DIMENSIONLESS_FRACTION  = "DIMENSIONLESS_FRACTION"    # 0–1 (e.g. RHO state variables)
    CONCENTRATION           = "CONCENTRATION"             # µM, nM, mol/L
    MOLECULAR_WEIGHT        = "MOLECULAR_WEIGHT"          # g/mol, Da
    LIPOPHILICITY           = "LIPOPHILICITY"             # log P (dimensionless ratio)
    POLAR_SURFACE_AREA      = "POLAR_SURFACE_AREA"        # Å²
    COUNT                   = "COUNT"                     # dimensionless integer
    DIMENSIONLESS           = "DIMENSIONLESS"             # generic dimensionless
    UNKNOWN_DIMENSION       = "UNKNOWN_DIMENSION"


# Unit conversion factors to a canonical reference unit per dimension.
# { dimension: { unit_string: scale_to_canonical } }
_UNIT_SCALES: dict[PhysicalDimension, dict[str, float]] = {
    PhysicalDimension.MAGNETIC_FLUX_DENSITY: {
        "T": 1.0, "mT": 1e-3, "uT": 1e-6, "nT": 1e-9,
    },
    PhysicalDimension.ACCELERATION: {
        "m/s^2": 1.0, "m/s2": 1.0, "g": 9.80665,
    },
    PhysicalDimension.ANGULAR_VELOCITY: {
        "rad/s": 1.0, "deg/s": 0.017453292519943295,
    },
    PhysicalDimension.ILLUMINANCE: {
        "lx": 1.0, "klx": 1e3,
    },
    PhysicalDimension.PRESSURE: {
        "Pa": 1.0, "hPa": 1e2, "kPa": 1e3, "atm": 101325.0, "bar": 1e5,
    },
    PhysicalDimension.CONCENTRATION: {
        "mol/L": 1.0, "M": 1.0, "mM": 1e-3, "uM": 1e-6, "nM": 1e-9, "pM": 1e-12,
    },
    PhysicalDimension.MOLECULAR_WEIGHT: {
        "g/mol": 1.0, "Da": 1.0, "kDa": 1e3,
    },
    PhysicalDimension.POLAR_SURFACE_AREA: {
        "A^2": 1.0, "Å^2": 1.0,
    },
    PhysicalDimension.DIMENSIONLESS_FRACTION: {
        "fraction": 1.0, "": 1.0,
    },
    PhysicalDimension.DIMENSIONLESS: {
        "": 1.0,
    },
}


def units_are_convertible(
    units_a: str,
    units_b: str,
    dimension: PhysicalDimension,
) -> bool:
    """Return True if both unit strings are registered for the given dimension."""
    scale_map = _UNIT_SCALES.get(dimension, {})
    return units_a in scale_map and units_b in scale_map


# ─────────────────────────────────────────────────────────────────────────────
# QuantityDescriptor
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class QuantityDescriptor:
    """
    Full semantic identity of a measured or computed quantity.

    Two QuantityDescriptors are comparable only if ALL of the following hold:
      1. semantic_name matches (e.g. "magnetic_flux_density_x" ≠ "acceleration_x")
      2. physical_dimension matches
      3. units are convertible within that dimension

    component_axis:
      For vector quantities, set to "x", "y", "z", or None for scalar/magnitude.
      Bx, By, Bz are distinct descriptors; |B| is a separate DERIVED descriptor.
    """
    # Semantic identity
    semantic_name: str           # e.g. "magnetic_flux_density_x"
    symbol: str                  # e.g. "Bx"
    description: str             # e.g. "Magnetic flux density, X component"

    # Physical typing
    physical_dimension: PhysicalDimension
    units: str                   # e.g. "uT"

    # Optional vector metadata
    component_axis: Optional[str] = None   # "x" | "y" | "z" | None

    # Epistemic metadata (for derived quantities like |B|)
    epistemic_state: EpistemicState = EpistemicState.MEASURED

    def is_comparable_to(self, other: "QuantityDescriptor") -> bool:
        """
        Full compatibility check: semantic identity + dimension + convertible units.
        Physical dimension alone is insufficient.
        """
        return (
            self.semantic_name == other.semantic_name
            and self.physical_dimension == other.physical_dimension
            and units_are_convertible(self.units, other.units, self.physical_dimension)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Canonical QuantityDescriptor library
# ─────────────────────────────────────────────────────────────────────────────

# Sensor stream quantities — vector components preserved
MAGNETIC_FIELD_X = QuantityDescriptor(
    semantic_name="magnetic_flux_density_x", symbol="Bx",
    description="Magnetic flux density, X component",
    physical_dimension=PhysicalDimension.MAGNETIC_FLUX_DENSITY,
    units="uT", component_axis="x",
)
MAGNETIC_FIELD_Y = QuantityDescriptor(
    semantic_name="magnetic_flux_density_y", symbol="By",
    description="Magnetic flux density, Y component",
    physical_dimension=PhysicalDimension.MAGNETIC_FLUX_DENSITY,
    units="uT", component_axis="y",
)
MAGNETIC_FIELD_Z = QuantityDescriptor(
    semantic_name="magnetic_flux_density_z", symbol="Bz",
    description="Magnetic flux density, Z component",
    physical_dimension=PhysicalDimension.MAGNETIC_FLUX_DENSITY,
    units="uT", component_axis="z",
)
MAGNETIC_FIELD_MAG = QuantityDescriptor(
    semantic_name="magnetic_flux_density_magnitude", symbol="|B|",
    description="Magnetic flux density magnitude (derived from Bx, By, Bz)",
    physical_dimension=PhysicalDimension.MAGNETIC_FLUX_DENSITY,
    units="uT", component_axis=None,
    epistemic_state=EpistemicState.DERIVED,
)

ACCELERATION_X = QuantityDescriptor(
    semantic_name="acceleration_x", symbol="ax",
    description="Linear acceleration, X axis",
    physical_dimension=PhysicalDimension.ACCELERATION,
    units="m/s^2", component_axis="x",
)
ACCELERATION_Y = QuantityDescriptor(
    semantic_name="acceleration_y", symbol="ay",
    description="Linear acceleration, Y axis",
    physical_dimension=PhysicalDimension.ACCELERATION,
    units="m/s^2", component_axis="y",
)
ACCELERATION_Z = QuantityDescriptor(
    semantic_name="acceleration_z", symbol="az",
    description="Linear acceleration, Z axis",
    physical_dimension=PhysicalDimension.ACCELERATION,
    units="m/s^2", component_axis="z",
)

ANGULAR_VELOCITY_X = QuantityDescriptor(
    semantic_name="angular_velocity_x", symbol="ωx",
    description="Angular velocity, X axis",
    physical_dimension=PhysicalDimension.ANGULAR_VELOCITY,
    units="rad/s", component_axis="x",
)
ANGULAR_VELOCITY_Y = QuantityDescriptor(
    semantic_name="angular_velocity_y", symbol="ωy",
    description="Angular velocity, Y axis",
    physical_dimension=PhysicalDimension.ANGULAR_VELOCITY,
    units="rad/s", component_axis="y",
)
ANGULAR_VELOCITY_Z = QuantityDescriptor(
    semantic_name="angular_velocity_z", symbol="ωz",
    description="Angular velocity, Z axis",
    physical_dimension=PhysicalDimension.ANGULAR_VELOCITY,
    units="rad/s", component_axis="z",
)

ILLUMINANCE = QuantityDescriptor(
    semantic_name="illuminance", symbol="Ev",
    description="Illuminance",
    physical_dimension=PhysicalDimension.ILLUMINANCE,
    units="lx",
)
PRESSURE = QuantityDescriptor(
    semantic_name="pressure", symbol="p",
    description="Atmospheric pressure",
    physical_dimension=PhysicalDimension.PRESSURE,
    units="hPa",
)

# RHO P23H simulation state variables
RHO_FOLDED_POOL = QuantityDescriptor(
    semantic_name="rho_p23h_folded_pool", symbol="R_f",
    description="RHO P23H — Folded rhodopsin pool (normalized)",
    physical_dimension=PhysicalDimension.DIMENSIONLESS_FRACTION,
    units="fraction",
)
RHO_ER_RETAINED = QuantityDescriptor(
    semantic_name="rho_p23h_er_retained", symbol="R_ER",
    description="RHO P23H — ER-retained misfolded pool (normalized)",
    physical_dimension=PhysicalDimension.DIMENSIONLESS_FRACTION,
    units="fraction",
)
RHO_SURFACE_POOL = QuantityDescriptor(
    semantic_name="rho_p23h_surface_pool", symbol="R_s",
    description="RHO P23H — Functional outer-segment surface pool (normalized)",
    physical_dimension=PhysicalDimension.DIMENSIONLESS_FRACTION,
    units="fraction",
)
RHO_STRESS = QuantityDescriptor(
    semantic_name="rho_p23h_stress", symbol="S",
    description="RHO P23H — Unfolded protein response / ER stress (normalized)",
    physical_dimension=PhysicalDimension.DIMENSIONLESS_FRACTION,
    units="fraction",
)
RHO_VIABILITY = QuantityDescriptor(
    semantic_name="rho_p23h_viability", symbol="V",
    description="RHO P23H — Photoreceptor viability (normalized)",
    physical_dimension=PhysicalDimension.DIMENSIONLESS_FRACTION,
    units="fraction",
)

# Ordered list matching RHO model state_schema()
RHO_STATE_QUANTITIES: list[QuantityDescriptor] = [
    RHO_FOLDED_POOL,
    RHO_ER_RETAINED,
    RHO_SURFACE_POOL,
    RHO_STRESS,
    RHO_VIABILITY,
]

# Chemistry engine outputs
CHEM_MOLECULAR_WEIGHT = QuantityDescriptor(
    semantic_name="molecular_weight", symbol="MW",
    description="Molecular weight",
    physical_dimension=PhysicalDimension.MOLECULAR_WEIGHT,
    units="g/mol",
    epistemic_state=EpistemicState.CALCULATED,
)
CHEM_LOGP = QuantityDescriptor(
    semantic_name="lipophilicity_logp", symbol="logP",
    description="Calculated octanol-water partition coefficient",
    physical_dimension=PhysicalDimension.LIPOPHILICITY,
    units="",
    epistemic_state=EpistemicState.CALCULATED,
)
CHEM_TPSA = QuantityDescriptor(
    semantic_name="polar_surface_area", symbol="TPSA",
    description="Topological polar surface area",
    physical_dimension=PhysicalDimension.POLAR_SURFACE_AREA,
    units="A^2",
    epistemic_state=EpistemicState.CALCULATED,
)

# Sensor quantity map — used by assemblers
SENSOR_QUANTITY_MAP: dict[str, list[QuantityDescriptor]] = {
    "MAGNETIC_FIELD": [MAGNETIC_FIELD_X, MAGNETIC_FIELD_Y, MAGNETIC_FIELD_Z, MAGNETIC_FIELD_MAG],
    "ACCELERATION":   [ACCELERATION_X, ACCELERATION_Y, ACCELERATION_Z],
    "ANGULAR_VELOCITY": [ANGULAR_VELOCITY_X, ANGULAR_VELOCITY_Y, ANGULAR_VELOCITY_Z],
    "ILLUMINANCE":    [ILLUMINANCE],
    "PRESSURE":       [PRESSURE],
}


# ─────────────────────────────────────────────────────────────────────────────
# ObservationKind
# ─────────────────────────────────────────────────────────────────────────────

class ObservationKind(Enum):
    SENSOR_STREAM    = "SENSOR_STREAM"
    CAMERA_FRAME     = "CAMERA_FRAME"
    MICROSCOPY       = "MICROSCOPY"
    SPECTROSCOPY     = "SPECTROSCOPY"
    ELECTROCHEMISTRY = "ELECTROCHEMISTRY"
    SIMULATION       = "SIMULATION"
    VIRTUAL_ASSAY    = "VIRTUAL_ASSAY"
    CHEMISTRY        = "CHEMISTRY"


# ─────────────────────────────────────────────────────────────────────────────
# ExperimentObservation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ExperimentObservation:
    """
    Base class for scientific observations attached to a VirtualExperiment.
    """
    observation_id: str
    experiment_id: str
    session_id: str
    instrument_id: str
    kind: ObservationKind
    quantities: List[QuantityDescriptor]
    artifact_path: str
    artifact_sha256: str
    acquisition_utc: str
    sample_count: int = 0
    duration_s: float = 0.0
    notes: Optional[str] = None
    calibration_id: Optional[str] = None

@dataclass(frozen=True)
class RawObservation(ExperimentObservation):
    """
    Immutable representation of raw physical measurements directly from the instrument.
    Cannot be modified. Must maintain EpistemicState.MEASURED.
    """
    epistemic_state: EpistemicState = field(default=EpistemicState.MEASURED, init=False)

@dataclass(frozen=True)
class NormalizedObservation(ExperimentObservation):
    """
    Observation derived via calibration, cleanup, or unit normalization.
    Must maintain EpistemicState.CALCULATED, DERIVED, or INFERRED.
    """
    epistemic_state: EpistemicState = EpistemicState.CALCULATED
    parent_observation_id: Optional[str] = None

    def __post_init__(self):
        if self.epistemic_state == EpistemicState.MEASURED:
            raise ValueError("NormalizedObservation cannot claim MEASURED epistemic state. It must be DERIVED, CALCULATED, or INFERRED.")
