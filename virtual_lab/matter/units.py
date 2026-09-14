import pint

ureg = pint.UnitRegistry()

# Define the canonical kernel units as prescribed by the architecture
# length: meter
# mass: kilogram
# time: second
# temperature: kelvin
# amount: mole
# charge: coulomb
# energy: joule
# pressure: pascal
# concentration: mole / meter**3

CANONICAL_UNITS = {
    '[length]': ureg.meter,
    '[mass]': ureg.kilogram,
    '[time]': ureg.second,
    '[temperature]': ureg.kelvin,
    '[substance]': ureg.mole,
    '[current] * [time]': ureg.coulomb,
    '[length] ** 2 * [mass] / [time] ** 2': ureg.joule,
    '[mass] / [length] / [time] ** 2': ureg.pascal,
    '[substance] / [length] ** 3': ureg.mole / ureg.meter**3
}

def to_canonical(value: float, unit: str) -> float:
    """Validate and convert an input unit to its canonical numerical value in the kernel."""
    quantity = value * ureg(unit)
    dimensionality = str(quantity.dimensionality)
    
    # Simple temperature conversion edge cases
    if dimensionality == '[temperature]':
        return quantity.to(ureg.kelvin).magnitude
        
    for dim_str, canonical_unit in CANONICAL_UNITS.items():
        if dimensionality == dim_str:
            return quantity.to(canonical_unit).magnitude
            
    # Fallback to base units
    return quantity.to_base_units().magnitude

def validate_dimensionality(unit: str, expected_dimensionality: str):
    quantity = 1.0 * ureg(unit)
    if str(quantity.dimensionality) != expected_dimensionality:
        raise ValueError(f"Expected dimensionality {expected_dimensionality}, got {quantity.dimensionality}")
