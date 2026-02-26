#!/usr/bin/env python3
"""
FFT Magnitude-Squared Oracle (float32)

Reference implementation for FFT kernel validation.
Computes one-sided |X[k]|^2 using numpy.fft.fft.
"""

import numpy as np
import sys


def fft_magsq_ref(input_data):
    """
    Compute one-sided magnitude-squared FFT spectrum.

    Args:
        input_data: Input array of shape (W, C) in float32

    Returns:
        Array of shape (W//2+1, C) in float32 (magnitude-squared)
    """
    W, C = input_data.shape
    output_bins = W // 2 + 1
    output = np.zeros((output_bins, C), dtype=np.float32)

    for c in range(C):
        # Match C kernel precision: float32 throughout
        X = np.fft.fft(input_data[:, c])
        mag_sq = (X[:output_bins].real ** 2 + X[:output_bins].imag ** 2)
        output[:, c] = mag_sq.astype(np.float32)

    return output


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        if len(sys.argv) < 3:
            print("Usage: python3 oracle.py --test <input_file> "
                  "[--output <output_file>] [--state <state_file>]")
            sys.exit(1)

        input_path = sys.argv[2]
        output_path = "/tmp/test_output.bin"

        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--output" and i + 1 < len(sys.argv):
                output_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--state" and i + 1 < len(sys.argv):
                i += 2  # Accept but ignore (FFT is stateless)
            else:
                i += 1

        # Load input (interleaved: sample-major)
        x = np.fromfile(input_path, dtype=np.float32)
        if x.size % 64 != 0:
            print(f"Error: Input size {x.size} not divisible by 64 channels")
            sys.exit(1)

        W = x.size // 64
        x = x.reshape(W, 64)

        y = fft_magsq_ref(x)
        y.astype(np.float32).tofile(output_path)
        print(f"[fft@f32] Processed: ({W}, 64) -> {y.shape}")
        sys.exit(0)

    # Self-test
    np.random.seed(42)
    W, C = 160, 64

    t = np.arange(W) / 160.0
    x = (
        np.sin(2 * np.pi * 10 * t)[:, None] * 50
        + np.random.randn(W, C).astype(np.float32) * 5
    )

    y = fft_magsq_ref(x)

    assert y.shape == (W // 2 + 1, C), f"Shape mismatch: {y.shape}"
    assert not np.any(np.isnan(y)), "Output contains NaNs"
    assert np.all(y >= 0), "Magnitude-squared must be non-negative"
    assert y.dtype == np.float32

    # Check dominant bin (10 Hz at fs=160, N=160 -> bin 10)
    bin_10_power = y[10, 0]
    median_power = np.median(y[:, 0])
    assert bin_10_power > 10 * median_power, \
        f"Expected dominant 10Hz bin, got {bin_10_power:.1f} vs median {median_power:.1f}"

    print(f"FFT f32 Oracle Self-Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Bin 10 power: {bin_10_power:.1f} (10Hz tone)")
    print(f"Median power: {median_power:.1f}")
    print("PASSED")
