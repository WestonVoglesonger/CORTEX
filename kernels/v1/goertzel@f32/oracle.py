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
    import sys
    import os
    
    # CLI test mode
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        if len(sys.argv) < 3:
            print("Usage: python3 oracle.py --test <input_file> [--output <output_file>] [--state <state_file>]")
            sys.exit(1)

        input_path = sys.argv[2]
        # Default paths (backward compatible)
        output_path = "/tmp/test_output.bin"
        state_path = "/tmp/goertzel_state.npy"
        
        # Parse optional --output and --state arguments
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--output" and i + 1 < len(sys.argv):
                output_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--state" and i + 1 < len(sys.argv):
                state_path = sys.argv[i + 1]
                i += 2
            else:
                print(f"Warning: Unknown argument {sys.argv[i]}")
                i += 1

        # Load input data (interleaved: [sample0_ch0, sample0_ch1, ..., sample0_ch63, sample1_ch0, ...])
        x = np.fromfile(input_path, dtype=np.float32)
        # Reshape to (W, C) assuming W=160, C=64 for now
        if x.size % 64 != 0:
            print(f"Error: Input size {x.size} not divisible by 64 channels")
            sys.exit(1)

        # Assume single window of 160 samples × 64 channels
        if x.size != 160 * 64:
            print(f"Error: Expected 10240 floats (160×64), got {x.size}")
            sys.exit(1)

        x = x.reshape(160, 64)

        # Goertzel is stateless, so no state loading needed
        # But we accept --state for compatibility with test infrastructure

        # Compute bandpower
        y = goertzel_bandpower_ref(x)

        # Write output (shape is (2, 64) = 128 floats)
        y.astype(np.float32).tofile(output_path)

        # Print info
        print(f"Processed {x.shape[0]} samples, {x.shape[1]} channels")
        print(f"Output shape: {y.shape} (B={y.shape[0]} bands, C={y.shape[1]} channels)")
        sys.exit(0)
    
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

