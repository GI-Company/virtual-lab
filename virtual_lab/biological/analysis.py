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
    
    # If y has zero variance, PRCC is 0 for all parameters
    if np.std(y_ranked) < 1e-12:
        return np.zeros(K)
        
    # Handle constant parameter columns so np.corrcoef doesn't produce NaN
    stds = np.std(data, axis=0)
    valid_cols = stds >= 1e-12
    if not np.all(valid_cols):
        valid_param_mask = valid_cols[:K]
        if not np.any(valid_param_mask):
            return np.zeros(K)
        sub_X = X[:, valid_param_mask]
        if sub_X.shape[1] == 1:
            # With a single non-constant predictor, partial rank correlation reduces to Spearman rank correlation
            x_r = rankdata(sub_X[:, 0])
            c = np.corrcoef(x_r, y_ranked)[0, 1]
            sub_prcc = np.array([0.0 if not np.isfinite(c) else float(np.clip(c, -1.0, 1.0))])
        else:
            sub_prcc = prcc(sub_X, y)
        full_prcc = np.zeros(K)
        full_prcc[valid_param_mask] = sub_prcc
        return full_prcc

    if K == 1:
        c = np.corrcoef(X_ranked[:, 0], y_ranked)[0, 1]
        return np.array([0.0 if not np.isfinite(c) else float(np.clip(c, -1.0, 1.0))])
    
    # 2. Compute correlation matrix
    with np.errstate(invalid="ignore", divide="ignore"):
        C = np.corrcoef(data, rowvar=False)
    C = np.nan_to_num(C, nan=0.0, posinf=0.0, neginf=0.0)
    
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
        prod = P[i, i] * P_YY
        if prod > 1e-24:
            den = np.sqrt(prod)
            if den > 1e-12:
                prccs[i] = np.clip(-P[i, K] / den, -1.0, 1.0)
            
    return prccs
