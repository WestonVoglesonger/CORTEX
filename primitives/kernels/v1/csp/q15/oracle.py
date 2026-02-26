#!/usr/bin/env python3
"""
CSP Oracle for Q15 data type.

Models the exact quantization error chain:
1. Load float32 calibration state (same as f32 variant)
2. Quantize spatial filters to Q15
3. Quantize input to Q15
4. Apply spatial filtering using integer arithmetic matching C kernel:
   - int64 accumulator for dot product (64ch × Q15×Q15 exceeds int32)
   - Round-to-nearest (>>15 with rounding bias)
   - Saturate output to Q15 range
5. Dequantize output to float32 for comparison
"""

import numpy as np
import os
import sys
import struct


def float_to_q15(x):
    """Convert float32 array to Q15 (int16) with clamping."""
    clamped = np.clip(x, -1.0, 1.0)
    scaled = np.round(clamped * 32768.0).astype(np.int64)
    return np.clip(scaled, -32768, 32767).astype(np.int16)


def q15_to_float(x):
    """Convert Q15 (int16) array to float32."""
    return x.astype(np.float32) / 32768.0


def load_csp_state(state_path):
    """Load CSP calibration state from .cortex_state file."""
    with open(state_path, 'rb') as f:
        header = f.read(16)
        if len(header) != 16:
            raise ValueError(f"Invalid state file: header too short ({len(header)} bytes)")

        magic, abi_version, state_version, state_size = struct.unpack('<IIII', header)
        if magic != 0x434F5254:
            raise ValueError(f"Invalid magic number: 0x{magic:08X}")

        payload = f.read(state_size)

    n_channels, n_components = struct.unpack('<II', payload[:8])
    filter_data = np.frombuffer(payload[8:], dtype='<f4')
    filters = filter_data.reshape((n_components, n_channels), order='F')

    return {
        'filters': filters.astype(np.float32),
        'n_channels': n_channels,
        'n_components': n_components,
    }


def csp_q15_oracle(input_data, state):
    """
    Q15-aware CSP reference implementation.

    Models the exact integer arithmetic path of the C kernel:
    - Filters quantized to Q15
    - int64 accumulator for dot product
    - Round-to-nearest shift >>15
    - Q15 output saturation

    Args:
        input_data: Input array of shape (W, C), float32
        state: CSP state dict with 'filters' [n_components, C]

    Returns:
        output_data: Output array of shape (W, n_components), float32 (dequantized Q15)
    """
    W, C = input_data.shape
    filters = state['filters']  # [n_components, C]
    n_components = filters.shape[0]

    # Step 1: Quantize filters to Q15 (column-major, matching C layout)
    # C layout: W_filters[k + c * K] for element (k, c) — column-major
    filters_q15 = float_to_q15(filters)  # [n_components, C] as int16

    # Step 2: Quantize input to Q15
    q15_in = float_to_q15(input_data)  # [W, C] as int16

    # Step 3: Matrix multiply in integer arithmetic
    q15_out = np.zeros((W, n_components), dtype=np.int16)

    for t in range(W):
        for k in range(n_components):
            acc = np.int64(0)
            for c in range(C):
                acc += np.int64(q15_in[t, c]) * np.int64(filters_q15[k, c])

            # Round-to-nearest: add 0.5 in Q30, shift >>15
            acc += (1 << 14)
            result = int(acc >> 15)

            # Saturate to Q15
            if result > 32767:
                result = 32767
            elif result < -32768:
                result = -32768

            q15_out[t, k] = np.int16(result)

    # Step 4: Dequantize to float32
    return q15_to_float(q15_out)


if __name__ == "__main__":
    # CLI test mode (matches validate.c calling convention)
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        if len(sys.argv) < 3:
            print("Usage: python3 oracle.py --test <input_file> [--output <output_file>] [--state <state_file>]")
            sys.exit(1)

        input_path = sys.argv[2]
        output_path = "/tmp/test_output.bin"
        state_path = None

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

        if not state_path:
            print("Error: --state argument required for CSP")
            sys.exit(1)

        # Load input
        x = np.fromfile(input_path, dtype=np.float32)
        if x.size != 160 * 64:
            print(f"Error: Expected 10240 floats (160x64), got {x.size}")
            sys.exit(1)
        x = x.reshape(160, 64)

        # Load state
        state = load_csp_state(state_path)

        # Apply Q15 CSP
        y = csp_q15_oracle(x, state)

        # Write output
        y.astype(np.float32).tofile(output_path)
        print(f"[csp@q15] Processed: {x.shape} -> {y.shape}")
        sys.exit(0)

    # Self-test mode
    np.random.seed(42)
    W, C = 160, 64
    n_components = 4

    # Create synthetic CSP filters
    filters = np.random.randn(n_components, C).astype(np.float32) * 0.1
    state = {'filters': filters, 'n_channels': C, 'n_components': n_components}

    # Create synthetic input
    x = np.random.randn(W, C).astype(np.float32) * 0.5

    # Run Q15 oracle
    y = csp_q15_oracle(x, state)

    assert y.shape == (W, n_components), f"Shape mismatch: {y.shape}"
    assert not np.any(np.isnan(y)), "Output contains NaNs"
    assert y.dtype == np.float32, f"Wrong dtype: {y.dtype}"

    print(f"CSP Q15 Oracle Self-Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Output range: [{y.min():.6f}, {y.max():.6f}]")
    print("PASSED")
