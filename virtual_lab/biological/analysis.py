import numpy as np
from scipy.stats import rankdata

def prcc(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """
    Computes the Partial Rank Correlation Coefficient (PRCC) between each column of X and y.
    
    Args:
        X: (N, K) array of sampled parameters (N samples, K parameters)
        y: (N,) array of output responses
        
    Returns:
        (K,) array of PRCC values
    """
    # Ensure 2D
    if X.ndim == 1:
        X = X.reshape(-1, 1)
        
    N, K = X.shape
    
    # 1. Rank transform the data
    X_ranked = np.zeros_like(X, dtype=float)
    for j in range(K):
        X_ranked[:, j] = rankdata(X[:, j])
    y_ranked = rankdata(y)
    
    # Combine into one matrix [X_1, ..., X_K, Y]
    data = np.column_stack((X_ranked, y_ranked))
    
    # 2. Compute correlation matrix
    C = np.corrcoef(data, rowvar=False)
    
    # 3. Invert correlation matrix
    try:
        P = np.linalg.pinv(C)
    except np.linalg.LinAlgError:
        # Fallback if degenerate
        return np.zeros(K)
        
    # 4. Compute PRCC
    # PRCC_{i, Y} = -P_{i, Y} / sqrt(P_{i,i} * P_{Y,Y})
    # Y is the last column index: K
    P_YY = P[K, K]
    
    prccs = np.zeros(K)
    for i in range(K):
        den = np.sqrt(P[i, i] * P_YY)
        if den > 1e-12:
            prccs[i] = -P[i, K] / den
            
    return prccs
