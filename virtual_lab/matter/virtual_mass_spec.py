"""Instrument-free isotope-envelope calculation for CHON molecular formulas.

This predicts composition-based centroids only. It does not predict ionization,
fragmentation, chromatography, detector response, or sample composition.
Representative isotope masses and abundances: NIST Atomic Weights and Isotopic
Compositions (https://pml.nist.gov/cgi-bin/Compositions/stand_alone.pl).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import argparse
import json
import re

from virtual_lab.domain.epistemics import EpistemicState

# (atomic mass in u, representative natural abundance). The abundance is a
# model assumption; natural isotope ratios vary across samples.
ISOTOPES = {
    "C": ((12.0, 0.9893), (13.00335483507, 0.0107)),
    "H": ((1.00782503223, 0.999885), (2.01410177812, 0.000115)),
    "N": ((14.00307400443, 0.99636), (15.00010889888, 0.00364)),
    "O": ((15.99491461957, 0.99757), (16.99913175650, 0.00038), (17.99915961286, 0.00205)),
}
PROTON_MASS_U = 1.007276466621
TOKEN = re.compile(r"([A-Z][a-z]?)([0-9]*)")


@dataclass(frozen=True)
class IsotopePeak:
    mz: float
    probability: float
    relative_intensity: float


@dataclass(frozen=True)
class VirtualSpectrum:
    formula: str
    ion: str
    charge: int
    epistemic_state: str
    peaks: tuple[IsotopePeak, ...]
    retained_probability: float
    omitted_probability: float
    model: str = "independent natural-abundance isotopes; protonated precursor"

    def to_dict(self) -> dict:
        return asdict(self)


def parse_formula(formula: str) -> dict[str, int]:
    """Parse an explicit, unparenthesized CHON formula; reject partial matches."""
    if not formula or len(formula) > 100:
        raise ValueError("Formula must contain 1–100 characters")
    counts: dict[str, int] = {}
    pos = 0
    for match in TOKEN.finditer(formula):
        if match.start() != pos:
            raise ValueError(f"Invalid formula near {formula[pos:]!r}")
        element, digits = match.groups()
        if element not in ISOTOPES:
            raise ValueError(f"Unsupported element {element}; supported: C, H, N, O")
        count = int(digits) if digits else 1
        if count < 1:
            raise ValueError("Element counts must be positive")
        counts[element] = counts.get(element, 0) + count
        pos = match.end()
    if pos != len(formula) or not counts:
        raise ValueError(f"Invalid formula near {formula[pos:]!r}")
    if sum(counts.values()) > 200:
        raise ValueError("Formula exceeds the 200-atom computational limit")
    return counts


def simulate_isotope_envelope(formula: str, charge: int = 1,
                              min_probability: float = 1e-10) -> VirtualSpectrum:
    """Return centroid m/z and probabilities for [M+zH]z+.

    States are keyed by isotope mass shift rounded to 1 micro-u, so near-
    identical isotopologues are merged. Pruned probability is disclosed.
    """
    counts = parse_formula(formula)
    if isinstance(charge, bool) or not isinstance(charge, int) or not 1 <= charge <= 5:
        raise ValueError("Charge must be an integer from 1 to 5")
    if not 0 < min_probability < 0.01:
        raise ValueError("min_probability must be between 0 and 0.01")
    base_mass = sum(count * ISOTOPES[element][0][0] for element, count in counts.items())
    states: dict[int, float] = {0: 1.0}
    for element, count in sorted(counts.items()):
        isotope_shifts = [(round((mass - ISOTOPES[element][0][0]) * 1_000_000), abundance)
                          for mass, abundance in ISOTOPES[element]]
        for _ in range(count):
            next_states: dict[int, float] = {}
            for shift, probability in states.items():
                for isotope_shift, abundance in isotope_shifts:
                    key = shift + isotope_shift
                    next_states[key] = next_states.get(key, 0.0) + probability * abundance
            states = {shift: probability for shift, probability in next_states.items()
                      if probability >= min_probability}
    retained = sum(states.values())
    if not states:
        raise ValueError("Probability cutoff removed every isotope peak")
    maximum = max(states.values())
    peaks = tuple(IsotopePeak(
        mz=(base_mass + shift / 1_000_000 + charge * PROTON_MASS_U) / charge,
        probability=probability,
        relative_intensity=100 * probability / maximum,
    ) for shift, probability in sorted(states.items()))
    return VirtualSpectrum(formula, f"[M+{charge}H]{charge}+", charge,
                           EpistemicState.SIMULATED.value, peaks, retained,
                           max(0.0, 1.0 - retained))


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a CHON precursor isotope envelope")
    parser.add_argument("formula", help="Unparenthesized formula, e.g. C6H12O6")
    parser.add_argument("--charge", type=int, default=1, help="Protonated ion charge (1–5)")
    parser.add_argument("--min-probability", type=float, default=1e-10)
    args = parser.parse_args()
    print(json.dumps(simulate_isotope_envelope(args.formula, args.charge,
                                               args.min_probability).to_dict(), indent=2))


if __name__ == "__main__":
    main()
