#!/usr/bin/env python3
"""
FIR Bandpass Filter Oracle

Reference implementation for FIR bandpass kernel validation.
"""

from scipy.signal import firwin, lfilter


def fir_bp_ref(x, fs=160.0, numtaps=129):
    """
    Apply FIR bandpass filter.
    
    Args:
        x: Input array of shape (W, C) in µV (float32)
        fs: Sampling rate (Hz). Default: 160.0
        numtaps: Number of filter taps. Default: 129
    
    Returns:
        y: Filtered output of shape (W, C) in µV (float32)
        b: Filter coefficients
    """
    b = firwin(numtaps, [8, 30], pass_zero=False, fs=fs, window='hamming')
    return lfilter(b, [1.0], x, axis=0).astype('float32'), b


if __name__ == "__main__":
    import numpy as np
    
    # Example usage and test
    np.random.seed(42)
    W, C = 160, 64
    
    # Generate synthetic data: mix of frequencies
    t = np.arange(W) / 160.0
    x = (
        np.sin(2 * np.pi * 5 * t)[:, None] * 10    # 5 Hz (below passband)
        + np.sin(2 * np.pi * 10 * t)[:, None] * 20  # 10 Hz (in passband)
        + np.sin(2 * np.pi * 25 * t)[:, None] * 15  # 25 Hz (in passband)
        + np.random.randn(W, C).astype(np.float32) * 5  # noise
    )
    
    # Apply FIR bandpass filter
    y, b = fir_bp_ref(x)
    
    print(f"FIR Bandpass Oracle Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Filter taps: {len(b)}")
    print(f"Passband: 8-30 Hz")
    print("Components outside passband should be attenuated")

