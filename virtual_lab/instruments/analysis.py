import numpy as np
from scipy import ndimage
from PySide6.QtGui import QImage
from typing import Tuple, Dict, Any, Optional

def jpeg_to_numpy(jpeg_bytes: bytes) -> np.ndarray:
    """
    Decodes exact source JPEG bytes into a strictly controlled NumPy array
    representing the source pixel coordinates.
    
    Returns an array of shape (height, width, channels) in RGB888 format.
    Does NOT apply any pyqtgraph-specific transposition.
    """
    img = QImage.fromData(jpeg_bytes, "JPEG")
    if img.isNull():
        raise ValueError("Failed to decode JPEG bytes.")
        
    # Force RGB888 format to guarantee channel ordering
    img = img.convertToFormat(QImage.Format_RGB888)
    
    ptr = img.constBits()
    # Pyside6 returns memoryview or sip.voidptr. Let's make sure it handles both.
    
    # Calculate bytes per line to ensure no padding issues, though RGB888 is usually packed tightly.
    # We'll reshape it to (height, width, 3)
    arr = np.array(ptr, copy=True).reshape((img.height(), img.width(), 3))
    return arr

def calculate_pixel_statistics(arr: np.ndarray, mask: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """
    Calculates deterministic pixel statistics for an image or ROI.
    arr: (H, W, 3) RGB array
    mask: boolean array of shape (H, W) where True means include pixel.
    """
    if mask is not None:
        if mask.shape != arr.shape[:2]:
            raise ValueError("Mask shape must match image spatial dimensions.")
        pixels = arr[mask]
    else:
        pixels = arr.reshape(-1, 3)
        
    if pixels.size == 0:
        return {}
        
    # Convert to grayscale for overall intensity stats (standard luminance)
    gray = np.dot(pixels[..., :3], [0.2989, 0.5870, 0.1140])
    
    stats = {
        "mean_intensity": float(np.mean(gray)),
        "median_intensity": float(np.median(gray)),
        "min_intensity": float(np.min(gray)),
        "max_intensity": float(np.max(gray)),
        "std_intensity": float(np.std(gray)),
        "mean_r": float(np.mean(pixels[:, 0])),
        "mean_g": float(np.mean(pixels[:, 1])),
        "mean_b": float(np.mean(pixels[:, 2])),
        "histogram": np.histogram(gray, bins=256, range=(0, 256))[0].tolist()
    }
    return stats

def threshold_connected_components(arr: np.ndarray, threshold: float, mask: Optional[np.ndarray] = None) -> Tuple[int, np.ndarray]:
    """
    Extracts DERIVED connected components using a simple threshold.
    Returns (num_components, labeled_array)
    """
    # Use grayscale for thresholding
    if len(arr.shape) == 3:
        gray = np.dot(arr[..., :3], [0.2989, 0.5870, 0.1140])
    else:
        gray = arr
        
    binary_mask = gray > threshold
    if mask is not None:
        binary_mask = binary_mask & mask
        
    # Label connected components
    labeled_array, num_features = ndimage.label(binary_mask)
    return num_features, labeled_array

def calculate_focus_metric(arr: np.ndarray, method: str = "TENENGRAD", mask: Optional[np.ndarray] = None) -> float:
    """
    Calculates a deterministic, relative focus-assist metric.
    arr: (H, W, 3) RGB array
    method: "TENENGRAD" (Gradient Energy) or "LAPLACIAN_VARIANCE"
    mask: Optional boolean array to restrict analysis to an ROI.
    """
    # Convert to grayscale
    if len(arr.shape) == 3:
        gray = np.dot(arr[..., :3], [0.2989, 0.5870, 0.1140])
    else:
        gray = arr
        
    if mask is not None:
        # We can't directly run sobel on a masked array easily without edge artifacts.
        # So we run sobel on the whole image and then take the mean over the mask.
        pass

    if method == "TENENGRAD":
        gx = ndimage.sobel(gray, axis=1)
        gy = ndimage.sobel(gray, axis=0)
        energy = gx**2 + gy**2
        if mask is not None:
            return float(np.mean(energy[mask]))
        return float(np.mean(energy))
    elif method == "LAPLACIAN_VARIANCE":
        lap = ndimage.laplace(gray)
        if mask is not None:
            return float(np.var(lap[mask]))
        return float(np.var(lap))
    else:
        raise ValueError(f"Unknown focus metric method: {method}")
