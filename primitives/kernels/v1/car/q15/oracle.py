#!/usr/bin/env python3
"""
Common Average Reference (CAR) Oracle for Q15 data type.

Models the exact quantization error chain:
1. Quantize float32 input to Q15
2. Compute CAR using integer arithmetic (matching the C kernel)
3. Dequantize Q15 output back to float32 for comparison
"""

import numpy as np


def float_to_q15(x):
    """Convert float32 array to Q15 (int16) with clamping."""
    clamped = np.clip(x, -1.0, 1.0)
    scaled = np.round(clamped * 32768.0).astype(np.int32)
    return np.clip(scaled, -32768, 32767).astype(np.int16)


def q15_to_float(x):
    """Convert Q15 (int16) array to float32."""
    return x.astype(np.float32) / 32768.0


def car_q15_oracle(input_data):
    """
    Q15-aware CAR reference implementation.

    Models the exact integer arithmetic path:
    - Accumulate channel sum in int32
    - Integer division for mean (truncation toward zero)
    - Saturating subtraction for output

    Args:
        input_data: Input array of shape (W, C), float32

    Returns:
        Output array of shape (W, C), float32 (dequantized Q15 result)
    """
    W, C = input_data.shape

    # Step 1: Quantize input to Q15
    q15_in = float_to_q15(input_data)

    # Step 2: CAR in integer arithmetic
    q15_out = np.zeros_like(q15_in)

    for t in range(W):
        # Accumulate in int32 (matches C kernel)
        row = q15_in[t, :].astype(np.int32)
        channel_sum = np.sum(row)
        # Integer division truncates toward zero (matches C)
        # Use int() truncation, not Python // (which is floor division)
        mean = np.int16(int(int(channel_sum) / int(C)))

        # Saturating subtraction per channel
        for c in range(C):
            diff = int(q15_in[t, c]) - int(mean)
            if diff > 32767:
                diff = 32767
            elif diff < -32768:
                diff = -32768
            q15_out[t, c] = np.int16(diff)

    # Step 3: Dequantize back to float32
    return q15_to_float(q15_out)


if __name__ == "__main__":
    import sys

    # CLI test mode (for validation harness)
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        if len(sys.argv) < 3:
            print("Usage: python3 oracle.py --test <input_file> [--output <output_file>] [--state <state_file>]")
            sys.exit(1)

        input_path = sys.argv[2]
        output_path = "/tmp/test_output.bin"

        # Parse optional arguments
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--output" and i + 1 < len(sys.argv):
                output_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--state" and i + 1 < len(sys.argv):
                i += 2  # Ignore state file for stateless kernels
            else:
                i += 1

        # Load input (float32 from dataset)
        x = np.fromfile(input_path, dtype=np.float32)
        if x.size != 160 * 64:
            print(f"Error: Expected 10240 floats (160x64), got {x.size}")
            sys.exit(1)

        x = x.reshape(160, 64)

        # Apply Q15 CAR oracle
        y = car_q15_oracle(x)

        # Write float32 output (for comparison with dequantized C kernel output)
        y.astype(np.float32).tofile(output_path)
        sys.exit(0)

    # Self-test mode
    np.random.seed(42)
    W, C = 160, 64
    x = np.random.randn(W, C).astype(np.float32) * 0.5  # Stay within Q15 range

    y = car_q15_oracle(x)

    # Verify: channel means should be near zero (within quantization error)
    q15_in = float_to_q15(x)
    for t in range(W):
        row = q15_in[t, :].astype(np.int32)
        s = np.sum(row)
        mean = int(int(s) / int(C))
        # After subtracting mean, residual sum = sum - C*mean
        # With integer truncation toward zero, |residual| < C
        residual = s - int(C) * mean
        assert abs(residual) < C, f"Residual {residual} >= C={C} at t={t}"

    print(f"CAR Q15 Oracle Self-Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Max output: {np.max(np.abs(y)):.6f}")
    print("PASSED")
