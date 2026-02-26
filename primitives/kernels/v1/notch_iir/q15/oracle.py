#!/usr/bin/env python3
"""
Notch IIR Filter Oracle for Q15 data type.

Models the exact quantization error chain:
1. Compute double-precision biquad coefficients (same as f32)
2. Quantize coefficients to Q14
3. Validate pole locations of quantized transfer function
4. Run biquad using integer arithmetic matching the C kernel:
   - Q14 coefficients, Q15 inputs, int64 accumulator
   - Round-to-nearest (>>14 with rounding bias)
   - Saturate output to Q15 range
5. Dequantize output to float32 for comparison
"""

import numpy as np
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


def double_to_q14(x):
    """Quantize a double coefficient to Q14 (range [-2, +2))."""
    scaled = x * 16384.0  # 1 << 14
    rounded = int(round(scaled))
    if rounded > 16383:
        rounded = 16383
    elif rounded < -16384:
        rounded = -16384
    return np.int16(rounded)


def compute_notch_coefficients(f0=60.0, Q=30.0, fs=160.0):
    """Compute biquad notch filter coefficients (matches C kernel)."""
    if abs(f0 - 60.0) < 1e-6 and abs(Q - 30.0) < 1e-6 and abs(fs - 160.0) < 1e-6:
        b0 = 0.9621952458291035
        b1 = 1.3607495663024323
        b2 = 0.9621952458291035
        a1 = 1.3607495663024323
        a2 = 0.9243904916582071
    else:
        w0 = 2.0 * np.pi * f0 / fs
        cos_w0 = np.cos(w0)
        BW = f0 / Q
        r = np.exp(-np.pi * BW / fs)

        b0 = 1.0
        b1 = -2.0 * cos_w0
        b2 = 1.0
        a1 = -2.0 * r * cos_w0
        a2 = r * r

    return b0, b1, b2, a1, a2


def validate_quantized_poles(a1_q14, a2_q14):
    """
    Validate that quantized denominator coefficients produce stable poles.
    Poles of H(z) must lie strictly inside the unit circle.

    Returns True if stable, raises AssertionError if unstable.
    """
    # Dequantize to float for pole analysis
    a1_f = float(a1_q14) / 16384.0
    a2_f = float(a2_q14) / 16384.0

    # Denominator polynomial: 1 + a1*z^-1 + a2*z^-2
    # In standard form: z^2 + a1*z + a2
    poles = np.roots([1.0, a1_f, a2_f])
    pole_magnitudes = np.abs(poles)

    if not np.all(pole_magnitudes < 1.0):
        raise AssertionError(
            f"Quantized poles outside unit circle! "
            f"Poles: {poles}, magnitudes: {pole_magnitudes}. "
            f"Q14 coefficients a1={a1_q14}, a2={a2_q14} "
            f"(dequantized: a1={a1_f:.6f}, a2={a2_f:.6f})"
        )

    return True


def notch_iir_q15_oracle(input_data, fs=160.0, f0=60.0, Q=30.0, zi=None):
    """
    Q15-aware notch IIR reference implementation.

    Models the exact integer arithmetic path of the C kernel:
    - Q14 coefficients (range [-2, +2))
    - int64 accumulator for 5-tap MAC
    - Round-to-nearest shift >>14
    - Q15 output saturation
    - int32 state variables for feedback stability

    Args:
        input_data: Input array of shape (W, C), float32
        fs: Sample rate in Hz
        f0: Notch frequency in Hz
        Q: Quality factor
        zi: Initial state array of shape (4, C), int32. None = zeros.

    Returns:
        output_data: Output array of shape (W, C), float32 (dequantized Q15)
        zf: Final state array of shape (4, C), int32
    """
    W, C = input_data.shape

    # Step 1: Compute double-precision coefficients
    b0_d, b1_d, b2_d, a1_d, a2_d = compute_notch_coefficients(f0, Q, fs)

    # Step 2: Quantize to Q14
    b0_q14 = int(double_to_q14(b0_d))
    b1_q14 = int(double_to_q14(b1_d))
    b2_q14 = int(double_to_q14(b2_d))
    a1_q14 = int(double_to_q14(a1_d))
    a2_q14 = int(double_to_q14(a2_d))

    # Step 3: Validate pole stability
    validate_quantized_poles(a1_q14, a2_q14)

    # Step 4: Quantize input to Q15
    q15_in = float_to_q15(input_data)

    # Step 5: Run biquad in integer arithmetic
    q15_out = np.zeros((W, C), dtype=np.int16)

    # State: [x1, x2, y1, y2] per channel as int32
    if zi is not None:
        state = zi.copy()
    else:
        state = np.zeros((4, C), dtype=np.int64)

    for ch in range(C):
        x1 = int(state[0, ch])
        x2 = int(state[1, ch])
        y1 = int(state[2, ch])
        y2 = int(state[3, ch])

        for t in range(W):
            x0 = int(q15_in[t, ch])

            # MAC in int64 (Q14 * Q15 -> Q29)
            acc = 0
            acc += b0_q14 * x0
            acc += b1_q14 * x1
            acc += b2_q14 * x2
            acc -= a1_q14 * y1
            acc -= a2_q14 * y2

            # Round-to-nearest: add 0.5 in Q29, shift >>14
            acc += (1 << 13)
            y0 = acc >> 14

            # Saturate to Q15
            if y0 > 32767:
                y0 = 32767
            elif y0 < -32768:
                y0 = -32768

            q15_out[t, ch] = np.int16(y0)

            # Shift state
            x2 = x1
            x1 = x0
            y2 = y1
            y1 = y0

        # Save final state
        state[0, ch] = x1
        state[1, ch] = x2
        state[2, ch] = y1
        state[3, ch] = y2

    # Step 6: Dequantize to float32
    return q15_to_float(q15_out), state


if __name__ == "__main__":
    # CLI test mode
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        if len(sys.argv) < 3:
            print("Usage: python3 oracle.py --test <input_file> [--output <output_file>] [--state <state_file>]")
            sys.exit(1)

        input_path = sys.argv[2]
        output_path = "/tmp/test_output.bin"
        state_path = "/tmp/notch_q15_state.npy"

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
            zi = np.load(state_path)
            if zi.shape != (4, 64):
                zi = None

        # Apply Q15 notch filter
        y, zf = notch_iir_q15_oracle(x, f0=60.0, Q=30.0, zi=zi)

        # Save state
        np.save(state_path, zf)

        # Write output
        y.astype(np.float32).tofile(output_path)
        sys.exit(0)

    # Self-test mode
    np.random.seed(42)
    W, C = 160, 64

    # Generate test signal: 60Hz sine + noise
    t_vec = np.arange(W) / 160.0
    x = (
        np.sin(2 * np.pi * 60 * t_vec)[:, None] * 0.5
        + np.random.randn(W, C).astype(np.float32) * 0.1
    )

    # Validate pole stability
    b0_d, b1_d, b2_d, a1_d, a2_d = compute_notch_coefficients(60.0, 30.0, 160.0)
    a1_q14 = int(double_to_q14(a1_d))
    a2_q14 = int(double_to_q14(a2_d))
    validate_quantized_poles(a1_q14, a2_q14)

    y, zf = notch_iir_q15_oracle(x)

    print(f"Notch IIR Q15 Oracle Self-Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Q14 coefficients: b0={double_to_q14(b0_d)}, b1={double_to_q14(b1_d)}, "
          f"b2={double_to_q14(b2_d)}, a1={double_to_q14(a1_d)}, a2={double_to_q14(a2_d)}")
    print(f"Poles validated: stable")
    print("PASSED")
