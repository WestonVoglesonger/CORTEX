#!/usr/bin/env python3
"""
Notch IIR Filter Oracle

Reference implementation for notch IIR kernel validation.
"""

from scipy.signal import iirnotch, lfilter


def notch_ref(x, fs=160.0, f0=60.0, Q=30.0, zi=None):
    """
    Apply notch IIR filter with state management.
    
    Args:
        x: Input array of shape (W, C) in µV (float32)
        fs: Sampling rate (Hz). Default: 160.0
        f0: Notch frequency (Hz). Default: 60.0
        Q: Quality factor. Default: 30.0
        zi: Initial filter state. If None, auto-initialize. Shape (2, C)
    
    Returns:
        y: Filtered output of shape (W, C) in µV (float32)
        zf: Final filter state (for state persistence)
    """
    b, a = iirnotch(f0, Q, fs=fs)
    if zi is None:
        y = lfilter(b, a, x, axis=0)
        return y.astype('float32'), None
    y, zf = lfilter(b, a, x, axis=0, zi=zi)
    return y.astype('float32'), zf


if __name__ == "__main__":
    import numpy as np
    
    # Example usage and test
    np.random.seed(42)
    W, C = 160, 64
    
    # Generate synthetic data: sine wave at 60 Hz + noise
    t = np.arange(W) / 160.0
    x = (
        np.sin(2 * np.pi * 60 * t)[:, None] * 10  # 60 Hz component
        + np.random.randn(W, C).astype(np.float32) * 5  # noise
    )
    
    # Apply notch filter
    y, zf = notch_ref(x, f0=60.0, Q=30.0)
    
    print(f"Notch IIR Oracle Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Filter state shape: {zf.shape if zf is not None else 'None'}")
    print(f"Notch at {60.0} Hz with Q={30.0}")
    print("60 Hz component should be attenuated")

