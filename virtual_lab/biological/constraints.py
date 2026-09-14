class BiologicalConstraintViolation(Exception):
    """Raised when a biological state violates a physical constraint (e.g., negative concentration)."""
    pass

class NumericalWarning(Warning):
    """Warning for small numerical excursions (e.g. -1e-10) that do not break biology but reflect solver limits."""
    pass

def enforce_non_negative(val: float, name: str, tolerance: float = -1e-8):
    if val < tolerance:
        raise BiologicalConstraintViolation(f"State {name} dropped below tolerance {tolerance}: {val}")
    elif val < 0:
        import warnings
        warnings.warn(f"Numerical excursion on {name}: {val}", NumericalWarning)

def enforce_bounds(val: float, name: str, lower: float = 0.0, upper: float = 1.0, tolerance: float = 1e-8):
    if val < lower - tolerance:
        raise BiologicalConstraintViolation(f"State {name} dropped below lower bound {lower}: {val}")
    if val > upper + tolerance:
        raise BiologicalConstraintViolation(f"State {name} exceeded upper bound {upper}: {val}")
