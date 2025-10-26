#!/usr/bin/env python3
"""
Common Average Reference (CAR) Oracle

Reference implementation for CAR kernel validation.
"""

import numpy as np


def car_ref(x):
    """
    Compute Common Average Reference.
    
    Args:
        x: Input array of shape (W, C) in µV (float32)
    
    Returns:
        Array of shape (W, C) in µV (float32) with channel means subtracted
    """
    m = np.nanmean(x, axis=1, keepdims=True)
    return (x - m).astype(np.float32)


if __name__ == "__main__":
    # Example usage and test
    np.random.seed(42)
    W, C = 160, 64
    
    # Generate synthetic data
    x = np.random.randn(W, C).astype(np.float32) * 100  # µV scale
    
    # Apply CAR
    y = car_ref(x)
    
    # Validate: mean across channels should be ≈ 0
    mean_per_time = np.mean(y, axis=1)
    max_deviation = np.max(np.abs(mean_per_time))
    
    print(f"CAR Oracle Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Max deviation from zero mean: {max_deviation:.6f} µV")
    print(f"Test {'PASSED' if max_deviation < 1e-4 else 'FAILED'}")

