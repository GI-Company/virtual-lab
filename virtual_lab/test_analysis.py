import numpy as np
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO))

from virtual_lab.biological.analysis import prcc

def test_prcc_basic():
    rng = np.random.default_rng(42)
    N = 1000
    
    # 3 parameters
    X1 = rng.uniform(0, 1, N)
    X2 = rng.uniform(0, 1, N)
    X3 = rng.uniform(0, 1, N)
    
    X = np.column_stack((X1, X2, X3))
    
    # Y = 2*X1 - 3*X2 + noise (X3 has no effect)
    Y = 2 * X1 - 3 * X2 + rng.normal(0, 0.1, N)
    
    prcc_vals = prcc(X, Y)
    
    assert len(prcc_vals) == 3
    # X1 should be strongly positive
    assert prcc_vals[0] > 0.8
    # X2 should be strongly negative
    assert prcc_vals[1] < -0.8
    # X3 should be near zero
    assert abs(prcc_vals[2]) < 0.1
