import pytest
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO))

from virtual_lab.matter.subatomic import PROTON, NEUTRON, ELECTRON
from virtual_lab.matter.elements import get_element
from virtual_lab.matter.isotopes import get_isotope
from virtual_lab.matter.atomic import AtomIdentity, AtomState
from virtual_lab.matter.units import to_canonical, validate_dimensionality
from virtual_lab.matter.serialization import serialize_dataclass
from virtual_lab.matter.hashing import deterministic_hash

def test_element_identity():
    carbon = get_element(6)
    assert carbon.atomic_number == 6
    assert carbon.symbol == "C"

def test_isotope_mass_defect():
    c13 = get_isotope(6, 13)
    assert c13.proton_count == 6
    assert c13.neutron_count == 7
    
    # 13C measured mass is ~13.00335
    assert abs(c13.measured_atomic_mass_u - 13.00335483507) < 1e-9
    
    # Constituent rest mass sum > measured mass due to mass defect (binding energy)
    assert c13.constituent_rest_mass_sum_u > c13.measured_atomic_mass_u
    assert c13.mass_defect_u > 0.0

def test_atom_state_charge():
    na23 = get_isotope(11, 23)
    
    # Neutral sodium atom
    na_neutral = AtomState(
        identity=AtomIdentity(isotope=na23),
        electron_count=11
    )
    assert na_neutral.formal_charge == 0
    
    # Sodium ion (Na+)
    na_ion = AtomState(
        identity=AtomIdentity(isotope=na23),
        electron_count=10
    )
    assert na_ion.formal_charge == 1

def test_unit_dimensionality():
    # Convert 10 uM to canonical (mol/m^3)
    val = to_canonical(10.0, "micromolar")
    # 10 umol/L = 10 * 1e-6 mol / (1e-3 m^3) = 1e-2 mol/m^3 = 0.01
    assert abs(val - 0.01) < 1e-6
    
    # Test dimension validation
    validate_dimensionality("micromolar", "[substance] / [length] ** 3")
    
    with pytest.raises(ValueError):
        validate_dimensionality("kilogram", "[substance] / [length] ** 3")

def test_identity_vs_state_hash():
    c13 = get_isotope(6, 13)
    c_identity = AtomIdentity(isotope=c13)
    
    c_neutral = AtomState(identity=c_identity, electron_count=6)
    c_ion = AtomState(identity=c_identity, electron_count=5)
    
    # Same identity hash
    assert c_neutral.identity.identity_hash == c_ion.identity.identity_hash
    
    # Different state hash
    assert c_neutral.state_hash != c_ion.state_hash

def test_serialization():
    na23 = get_isotope(11, 23)
    na_neutral = AtomState(
        identity=AtomIdentity(isotope=na23),
        electron_count=11
    )
    
    data = serialize_dataclass(na_neutral)
    
    # Should be a dict
    assert isinstance(data, dict)
    assert data["electron_count"] == 11
    
    # Nested dataclass serialized
    assert data["identity"]["isotope"]["mass_number"] == 23

    # Hashing should be deterministic
    h1 = deterministic_hash(data)
    h2 = deterministic_hash(serialize_dataclass(na_neutral))
    assert h1 == h2
