#!/usr/bin/env python3
"""
FFT Magnitude-Squared Oracle (Q15)

Models the fixed-point arithmetic of the C kernel:
- Input: Q15 (int16)
- FFT: kiss_fft with FIXED_POINT=16 (C_FIXDIV per-stage scaling)
- Output: Q15 magnitude-squared with Q30->Q15 shift

NOTE ON ORACLE ACCURACY:
kiss_fft's C_FIXDIV applies DIVSCALAR(x, k) = sround(smul(x, SAMP_MAX / k))
at each butterfly stage, where k depends on the radix factorization path.
The accumulated scaling is approximately 1/N but NOT exactly 1/N — the
per-stage rounding differs from a single divide-by-N. This oracle models
scaling as "divide by N" which is an approximation. The relaxed tolerance
(rtol=5e-2) absorbs the gap. For power-of-2 sizes the approximation is
tighter; for mixed-radix (e.g., N=160 = 2^5 * 5) it diverges more.
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


def fft_magsq_q15_ref(input_data):
    """
    Q15-aware FFT magnitude-squared reference.

    Models the C kernel's fixed-point behavior:
    1. Quantize input to Q15 (introduces quantization noise)
    2. Float FFT of dequantized Q15 input
    3. Divide by N (approximates accumulated C_FIXDIV scaling)
    4. Magnitude-squared
    5. Quantize result to Q15

    Args:
        input_data: Input array of shape (W, C) in float32

    Returns:
        Array of shape (W//2+1, C) in float32 (dequantized Q15)
    """
    W, C = input_data.shape
    output_bins = W // 2 + 1

    # Step 1: Quantize to Q15 and back (models quantization noise)
    q15_in = float_to_q15(input_data)
    dequantized = q15_to_float(q15_in)

    q15_out = np.zeros((output_bins, C), dtype=np.int16)

    for c in range(C):
        # Step 2: Float FFT of dequantized input (float32 precision)
        X = np.fft.fft(dequantized[:, c])

        # Step 3: Approximate C_FIXDIV scaling as 1/N
        X_scaled = X / W

        # Step 4: One-sided magnitude-squared
        X_onesided = X_scaled[:output_bins]
        mag_sq = X_onesided.real ** 2 + X_onesided.imag ** 2

        # Step 5: Scale to Q15 range and quantize
        # mag_sq is in float with values roughly in [0, 1] range after /N scaling
        # The C kernel computes in Q30 (Q15*Q15) then shifts >>15 to Q15
        # We model this as: convert mag_sq from float to Q15 representation
        q15_vals = np.round(mag_sq * 32768.0).astype(np.int64)
        q15_vals = np.clip(q15_vals, 0, 32767)  # mag-sq is non-negative
        q15_out[:, c] = q15_vals.astype(np.int16)

    return q15_to_float(q15_out)


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

        # Load input (interleaved float32, will be quantized to Q15)
        x = np.fromfile(input_path, dtype=np.float32)
        if x.size % 64 != 0:
            print(f"Error: Input size {x.size} not divisible by 64 channels")
            sys.exit(1)

        W = x.size // 64
        x = x.reshape(W, 64)

        y = fft_magsq_q15_ref(x)
        y.astype(np.float32).tofile(output_path)
        print(f"[fft@q15] Processed: ({W}, 64) -> {y.shape}")
        sys.exit(0)

    # Self-test: full-scale sinusoid to verify dominant bin is nonzero
    np.random.seed(42)
    W, C = 160, 4  # Small channel count for self-test

    # Generate full-scale Q15 sinusoid at bin k=10 (10 Hz at fs=160)
    t = np.arange(W) / 160.0
    amplitude = 0.99  # Near full-scale Q15
    x = np.zeros((W, C), dtype=np.float32)
    x[:, 0] = amplitude * np.sin(2 * np.pi * 10 * t)
    x[:, 1] = amplitude * np.sin(2 * np.pi * 20 * t)
    x[:, 2] = np.random.randn(W).astype(np.float32) * 0.1
    x[:, 3] = np.zeros(W, dtype=np.float32)  # Silence

    y = fft_magsq_q15_ref(x)

    assert y.shape == (W // 2 + 1, C), f"Shape mismatch: {y.shape}"
    assert not np.any(np.isnan(y)), "Output contains NaNs"
    assert np.all(y >= 0), "Magnitude-squared must be non-negative"

    # Check dominant bin for channel 0 (10 Hz -> bin 10)
    bin_10_power = y[10, 0]
    assert bin_10_power > 0, \
        f"Full-scale 10Hz tone produced zero at bin 10 (C_FIXDIV attenuation too severe)"
    median_power = np.median(y[:, 0])
    if median_power > 0:
        assert bin_10_power > 10 * median_power, \
            f"Expected dominant 10Hz bin: {bin_10_power:.6f} vs median {median_power:.6f}"

    # Check dominant bin for channel 1 (20 Hz -> bin 20)
    bin_20_power = y[20, 1]
    assert bin_20_power > 0, \
        f"Full-scale 20Hz tone produced zero at bin 20"

    # Silent channel should be all zeros (or near-zero from quantization noise)
    assert y[:, 3].max() < 1e-3, \
        f"Silent channel has nonzero output: max={y[:, 3].max()}"

    print("FFT Q15 Oracle Self-Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Bin 10 power (ch0, 10Hz): {bin_10_power:.6f}")
    print(f"Bin 20 power (ch1, 20Hz): {bin_20_power:.6f}")
    print(f"Silent channel max: {y[:, 3].max():.6f}")
    print("PASSED")
