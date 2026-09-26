import pytest

from virtual_lab.matter.virtual_mass_spec import parse_formula, simulate_isotope_envelope


def test_carbon_isotope_ratio_and_mass_spacing():
    spectrum = simulate_isotope_envelope("C")
    assert spectrum.epistemic_state == "SIMULATED"
    assert len(spectrum.peaks) == 2
    assert spectrum.peaks[1].mz - spectrum.peaks[0].mz == pytest.approx(1.00335483507, abs=1e-6)
    assert spectrum.peaks[1].probability / spectrum.peaks[0].probability == pytest.approx(0.0107 / 0.9893)
    assert spectrum.retained_probability == pytest.approx(1)


def test_charge_halves_isotope_spacing():
    one = simulate_isotope_envelope("C", 1)
    two = simulate_isotope_envelope("C", 2)
    assert two.peaks[1].mz - two.peaks[0].mz == pytest.approx((one.peaks[1].mz - one.peaks[0].mz) / 2)


def test_reproducible_and_discloses_pruning():
    a = simulate_isotope_envelope("C6H12O6", min_probability=1e-5)
    assert a == simulate_isotope_envelope("C6H12O6", min_probability=1e-5)
    assert a.omitted_probability > 0
    assert a.retained_probability + a.omitted_probability == pytest.approx(1)


@pytest.mark.parametrize("formula", ["", "C0", "C6(H2O)6", "C6H12O6!", "NaCl", "C201", "c6"])
def test_invalid_formula(formula):
    with pytest.raises(ValueError):
        parse_formula(formula)
