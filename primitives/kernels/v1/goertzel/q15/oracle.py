#!/usr/bin/env python3
"""
Goertzel Bandpower Oracle for Q15 data type.

Models the exact mixed-precision arithmetic of the C kernel:
- Input: Q15
- Goertzel coefficient: Q14 (range [-2, +2))
- Recurrence state: Q15 in int32 (with saturation)
- Power computation: int64
- Output: Q15 (scaled power)
"""

import numpy as np
import sys


def float_to_q15(x):
    """Convert float32 array to Q15 (int16) with clamping."""
    clamped = np.clip(x, -1.0, 1.0)
    scaled = np.round(clamped * 32768.0).astype(np.int64)
    return np.clip(scaled, -32768, 32767).astype(np.int16)


def q15_to_float(x):
    """Convert Q15 (int16) array to float32."""
    return x.astype(np.float32) / 32768.0


def double_to_q14(x):
    """Quantize a double coefficient to Q14 (range [-2, +2)) stored in int16."""
    scaled = x * 16384.0
    rounded = int(round(scaled))
    # int16 range [-32768, 32767] maps to [-2.0, ~2.0) in Q14
    if rounded > 32767:
        rounded = 32767
    elif rounded < -32768:
        rounded = -32768
    return np.int16(rounded)


def q14_mul_q15(coeff_q14, state_q15):
    """Q14 coefficient × Q15 state → Q15 result (with rounding)."""
    product = int(coeff_q14) * int(state_q15)
    return int((product + (1 << 13)) >> 14)


def goertzel_q15_oracle(input_data, fs=160.0,
                         bands=None):
    """
    Q15-aware Goertzel bandpower reference.

    Models the exact integer arithmetic of the C kernel with
    Q14 coefficients and Q15 state.

    Args:
        input_data: Input array of shape (W, C), float32
        fs: Sample rate in Hz
        bands: Dict of frequency bands. Default: alpha(8-13), beta(13-30)

    Returns:
        output_data: Array of shape (2, C), float32 (dequantized Q15 power)
    """
    if bands is None:
        bands = {'alpha': (8, 13), 'beta': (13, 30)}

    W, C = input_data.shape

    # Compute bin ranges
    band_bins = {}
    for name, (lo, hi) in bands.items():
        k_start = round(lo * W / fs)
        k_end = round(hi * W / fs)
        band_bins[name] = (k_start, k_end)

    # Overall bin range (alpha_start to beta_end)
    all_bins = [(s, e) for s, e in band_bins.values()]
    global_start = min(s for s, e in all_bins)
    global_end = max(e for s, e in all_bins)
    total_bins = global_end - global_start + 1

    # Quantize input to Q15
    q15_in = float_to_q15(input_data)

    # Compute Q14 coefficients
    coeffs_q14 = []
    for k in range(global_start, global_end + 1):
        omega = 2.0 * np.pi * k / W
        coeff = 2.0 * np.cos(omega)
        coeffs_q14.append(int(double_to_q14(coeff)))

    # Goertzel recurrence (integer arithmetic)
    s1 = np.zeros((total_bins, C), dtype=np.int64)  # Use int64 for Python overflow safety
    s2 = np.zeros((total_bins, C), dtype=np.int64)

    for n in range(W):
        for b in range(total_bins):
            coeff = coeffs_q14[b]
            for ch in range(C):
                x_val = int(q15_in[n, ch])

                # Q14 × Q15 → Q15 (with rounding)
                cs1 = q14_mul_q15(coeff, int(s1[b, ch]))
                s0 = x_val + cs1 - int(s2[b, ch])

                # Saturate to Q15 range
                if s0 > 32767:
                    s0 = 32767
                elif s0 < -32768:
                    s0 = -32768

                s2[b, ch] = s1[b, ch]
                s1[b, ch] = s0

    # Compute power per band
    q15_out = np.zeros((2, C), dtype=np.int16)
    band_list = list(bands.keys())

    for band_idx, name in enumerate(band_list):
        k_start, k_end = band_bins[name]
        for ch in range(C):
            power = np.int64(0)
            for k in range(k_start, k_end + 1):
                b = k - global_start
                s1v = int(s1[b, ch])
                s2v = int(s2[b, ch])
                coeff_v = coeffs_q14[b]

                # P_k = s1² + s2² - coeff*s1*s2
                pk = s1v * s1v + s2v * s2v
                cross = int((coeff_v * s1v * s2v + (1 << 13)) >> 14)
                pk -= cross

                power += pk

            # Scale: divide by W, shift >>15
            scaled = int(power) // W
            scaled = (scaled + (1 << 14)) >> 15
            if scaled > 32767:
                scaled = 32767
            elif scaled < -32768:
                scaled = -32768
            q15_out[band_idx, ch] = np.int16(scaled)

    return q15_to_float(q15_out)


if __name__ == "__main__":
    # CLI test mode
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        if len(sys.argv) < 3:
            print("Usage: python3 oracle.py --test <input_file> [--output <output_file>]")
            sys.exit(1)

        input_path = sys.argv[2]
        output_path = "/tmp/test_output.bin"

        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--output" and i + 1 < len(sys.argv):
                output_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--state" and i + 1 < len(sys.argv):
                i += 2  # Accept but ignore (Goertzel is stateless)
            else:
                i += 1

        # Load input
        x = np.fromfile(input_path, dtype=np.float32)
        if x.size != 160 * 64:
            print(f"Error: Expected 10240 floats (160x64), got {x.size}")
            sys.exit(1)
        x = x.reshape(160, 64)

        y = goertzel_q15_oracle(x)
        y.astype(np.float32).tofile(output_path)
        print(f"[goertzel@q15] Processed: {x.shape} -> {y.shape}")
        sys.exit(0)

    # Self-test
    np.random.seed(42)
    W, C = 160, 64

    t_vec = np.arange(W) / 160.0
    x = (
        np.sin(2 * np.pi * 10 * t_vec)[:, None] * 0.5   # Alpha
        + np.sin(2 * np.pi * 20 * t_vec)[:, None] * 0.3  # Beta
        + np.random.randn(W, C).astype(np.float32) * 0.05
    )

    y = goertzel_q15_oracle(x)

    assert y.shape == (2, C), f"Shape mismatch: {y.shape}"
    assert not np.any(np.isnan(y)), "Output contains NaNs"
    assert y.dtype == np.float32

    print(f"Goertzel Q15 Oracle Self-Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Alpha power range: [{y[0].min():.6f}, {y[0].max():.6f}]")
    print(f"Beta power range:  [{y[1].min():.6f}, {y[1].max():.6f}]")
    print("PASSED")
