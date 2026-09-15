import pytest
import numpy as np
from virtual_lab.instruments.analysis import calculate_pixel_statistics, threshold_connected_components

def test_pixel_statistics():
    # 2x2 image, 3 channels
    arr = np.array([
        [[255, 0, 0], [0, 255, 0]],
        [[0, 0, 255], [255, 255, 255]]
    ], dtype=np.uint8)
    
    stats = calculate_pixel_statistics(arr)
    # The gray conversion uses [0.2989, 0.5870, 0.1140]
    # Red: 255 * 0.2989 = 76.2195
    # Green: 255 * 0.5870 = 149.685
    # Blue: 255 * 0.1140 = 29.07
    # White: 255
    assert "mean_intensity" in stats
    assert "histogram" in stats
    assert len(stats["histogram"]) == 256
    
    # mean R should be (255+0+0+255)/4 = 127.5
    assert stats["mean_r"] == 127.5
    assert stats["mean_g"] == 127.5
    assert stats["mean_b"] == 127.5

def test_threshold_connected_components():
    # 3x3 array, mostly black with a white square in top left and bottom right
    arr = np.zeros((3, 3, 3), dtype=np.uint8)
    arr[0, 0] = [255, 255, 255]
    arr[2, 2] = [255, 255, 255]
    
    num_features, labels = threshold_connected_components(arr, threshold=128)
    assert num_features == 2
    assert labels[0, 0] > 0
    assert labels[2, 2] > 0
    assert labels[0, 1] == 0

def test_pixel_statistics_with_mask():
    arr = np.ones((2, 2, 3), dtype=np.uint8) * 100
    arr[0, 0] = [255, 255, 255]
    
    mask = np.array([
        [True, False],
        [False, False]
    ])
    
    stats = calculate_pixel_statistics(arr, mask)
    # Since we only include the top-left pixel (which is [255, 255, 255]),
    # mean should be 255 * 0.9999 = 254.9745
    assert stats["mean_intensity"] == pytest.approx(254.9745, rel=1e-3)
    assert stats["mean_r"] == 255.0

def test_spatial_calibration_mpp():
    # Simple math test mirroring optical_panel.py logic
    dx = 100.0
    dy = 0.0
    pixel_dist = np.sqrt(dx**2 + dy**2)
    
    dist_mm = 2.5
    dist_um = dist_mm * 1000.0
    mpp = dist_um / pixel_dist
    
    assert mpp == 25.0
