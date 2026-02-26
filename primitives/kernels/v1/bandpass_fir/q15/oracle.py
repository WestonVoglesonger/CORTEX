#!/usr/bin/env python3
"""
FIR Bandpass Filter Oracle for Q15 data type.

Models the exact quantization error chain:
1. Quantize FIR coefficients to Q15
2. Quantize input to Q15
3. Run FIR convolution using integer arithmetic matching C kernel:
   - Q15 coefficients × Q15 samples → Q30 products
   - int64 accumulator (129 taps × max product ≈ 138.5 billion)
   - Round-to-nearest (>>15 with rounding bias)
   - Saturate output to Q15 range
4. Dequantize output to float32 for comparison
"""

import numpy as np
from scipy.signal import firwin
import os
import sys


def float_to_q15(x):
    """Convert float32 array to Q15 (int16) with clamping."""
    clamped = np.clip(x, -1.0, 1.0)
    scaled = np.round(clamped * 32768.0).astype(np.int64)
    return np.clip(scaled, -32768, 32767).astype(np.int16)


def q15_to_float(x):
    """Convert Q15 (int16) array to float32."""
    return x.astype(np.float32) / 32768.0


def bandpass_fir_q15_oracle(input_data, fs=160.0, numtaps=129, zi=None):
    """
    Q15-aware FIR bandpass reference implementation.

    Args:
        input_data: Input array of shape (W, C), float32
        fs: Sample rate in Hz
        numtaps: Number of filter taps
        zi: Initial tail buffer of shape (numtaps-1, C), int16. None = zeros.

    Returns:
        output_data: Output array of shape (W, C), float32 (dequantized Q15)
        zf: Final tail buffer of shape (numtaps-1, C), int16
    """
    W, C = input_data.shape
    tail_len = numtaps - 1

    # Step 1: Compute and quantize coefficients to Q15
    b = firwin(numtaps, [8, 30], pass_zero=False, fs=fs, window='hamming')
    coeff_q15 = float_to_q15(b.astype(np.float32))

    # Step 2: Quantize input to Q15
    q15_in = float_to_q15(input_data)

    # Step 3: Set up tail buffer
    if zi is not None:
        tail = zi.copy()
    else:
        tail = np.zeros((tail_len, C), dtype=np.int16)

    # Step 4: FIR convolution in integer arithmetic
    q15_out = np.zeros((W, C), dtype=np.int16)

    for ch in range(C):
        for t in range(W):
            acc = np.int64(0)

            for k in range(numtaps):
                if k <= t:
                    x_val = int(q15_in[t - k, ch])
                else:
                    tail_idx = tail_len - (k - t)
                    if 0 <= tail_idx < tail_len:
                        x_val = int(tail[tail_idx, ch])
                    else:
                        x_val = 0

                acc += np.int64(coeff_q15[k]) * np.int64(x_val)

            # Round-to-nearest: add 0.5 in Q30, shift >>15
            acc += (1 << 14)
            result = int(acc >> 15)

            # Saturate to Q15
            if result > 32767:
                result = 32767
            elif result < -32768:
                result = -32768

            q15_out[t, ch] = np.int16(result)

    # Step 5: Update tail buffer (matches C kernel logic)
    hop_samples = W // 2  # Default 50% overlap
    if hop_samples < tail_len:
        shift_amount = hop_samples
        keep_amount = tail_len - shift_amount
        new_tail = np.zeros((tail_len, C), dtype=np.int16)
        new_tail[:keep_amount, :] = tail[shift_amount:, :]
        samples_to_copy = min(hop_samples, W)
        new_tail[keep_amount:keep_amount + samples_to_copy, :] = q15_in[:samples_to_copy, :]
    else:
        new_tail = np.zeros((tail_len, C), dtype=np.int16)
        if W >= tail_len:
            if hop_samples < W:
                src_start = hop_samples - tail_len
                new_tail[:, :] = q15_in[src_start:src_start + tail_len, :]
            else:
                new_tail[:, :] = q15_in[W - tail_len:W, :]
        else:
            new_tail[:W, :] = q15_in[:, :]

    # Step 6: Dequantize to float32
    return q15_to_float(q15_out), new_tail


if __name__ == "__main__":
    # CLI test mode
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        if len(sys.argv) < 3:
            print("Usage: python3 oracle.py --test <input_file> [--output <output_file>] [--state <state_file>]")
            sys.exit(1)

        input_path = sys.argv[2]
        output_path = "/tmp/test_output.bin"
        state_path = "/tmp/fir_q15_state.npy"

        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--output" and i + 1 < len(sys.argv):
                output_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--state" and i + 1 < len(sys.argv):
                state_path = sys.argv[i + 1]
                i += 2
            else:
                i += 1

        # Load input
        x = np.fromfile(input_path, dtype=np.float32)
        if x.size != 160 * 64:
            print(f"Error: Expected 10240 floats (160x64), got {x.size}")
            sys.exit(1)
        x = x.reshape(160, 64)

        # Load persistent state
        zi = None
        if os.path.exists(state_path):
            zi_loaded = np.load(state_path)
            if zi_loaded.shape == (128, 64) and zi_loaded.dtype == np.int16:
                zi = zi_loaded

        # Apply Q15 FIR bandpass
        y, zf = bandpass_fir_q15_oracle(x, zi=zi)

        # Save state
        np.save(state_path, zf)

        # Write output
        y.astype(np.float32).tofile(output_path)
        print(f"[bandpass_fir@q15] Processed: {x.shape} -> {y.shape}")
        sys.exit(0)

    # Self-test mode
    np.random.seed(42)
    W, C = 160, 64

    # Generate synthetic data
    t_vec = np.arange(W) / 160.0
    x = (
        np.sin(2 * np.pi * 5 * t_vec)[:, None] * 0.3   # Below passband
        + np.sin(2 * np.pi * 15 * t_vec)[:, None] * 0.5  # In passband
        + np.random.randn(W, C).astype(np.float32) * 0.1
    )

    y, zf = bandpass_fir_q15_oracle(x)

    assert y.shape == (W, C), f"Shape mismatch: {y.shape}"
    assert not np.any(np.isnan(y)), "Output contains NaNs"
    assert y.dtype == np.float32, f"Wrong dtype: {y.dtype}"
    assert zf.shape == (128, C), f"Tail shape mismatch: {zf.shape}"

    print(f"Bandpass FIR Q15 Oracle Self-Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Output range: [{y.min():.6f}, {y.max():.6f}]")
    print(f"Tail shape: {zf.shape}")
    print("PASSED")
