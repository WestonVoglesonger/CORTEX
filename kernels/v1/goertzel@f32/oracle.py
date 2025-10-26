#!/usr/bin/env python3
"""
Goertzel Bandpower Oracle

Reference implementation for Goertzel bandpower kernel validation.
"""

import numpy as np


def goertzel_bandpower_ref(x, fs=160.0, bands={'alpha':(8,13), 'beta':(13,30)}):
    """
    Compute bandpower using Goertzel algorithm.
    
    Args:
        x: Input array of shape (W, C) in µV (float32), W must be 160
        fs: Sampling rate (Hz). Default: 160.0
        bands: Dictionary of {name: (low, high)} frequency bands.
               Default: {'alpha':(8,13), 'beta':(13,30)}
    
    Returns:
        Array of shape (B, C) in µV² (float32) where B = number of bands
    """
    # x: (W,C) in µV, W must be 160
    N = x.shape[0]
    out = []
    for (lo, hi) in bands.values():
        ks = np.arange(lo, hi+1, dtype=float)
        omega = 2*np.pi*ks/N
        coeff = 2*np.cos(omega)[:,None]             # (bins,1)
        # run per bin via vectorized recurrence
        s0 = np.zeros((len(ks), x.shape[1])); s1 = s0.copy(); s2 = s0.copy()
        for n in range(N):
            s0 = x[n][None,:] + coeff*s1 - s2
            s2, s1 = s1, s0
        Pk = s1*s1 + s2*s2 - coeff*s1*s2           # (bins,C)
        out.append(Pk.sum(axis=0))                  # sum over bins -> (C,)
    return np.vstack(out).astype('float32')        # (B,C)


if __name__ == "__main__":
    # Example usage and test
    np.random.seed(42)
    W, C = 160, 64
    
    # Generate synthetic data with known frequency content
    t = np.arange(W) / 160.0
    x = (
        np.sin(2 * np.pi * 10 * t)[:, None] * 50   # 10 Hz in alpha band
        + np.sin(2 * np.pi * 20 * t)[:, None] * 30  # 20 Hz in beta band
        + np.random.randn(W, C).astype(np.float32) * 5  # noise
    )
    
    # Compute bandpower
    y = goertzel_bandpower_ref(x)
    
    print(f"Goertzel Bandpower Oracle Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Bands: alpha (8-13 Hz), beta (13-30 Hz)")
    print("Power in alpha and beta bands computed")

