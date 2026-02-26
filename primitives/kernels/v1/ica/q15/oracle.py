#!/usr/bin/env python3
"""
ICA Oracle for Q15 data type.

Models the exact quantization error chain:
1. Load float32 calibration state (mean + unmixing matrix)
2. Quantize mean and W_unmix to Q15
3. Quantize input to Q15
4. Apply unmixing: y = (x - mean) @ W.T using integer arithmetic
5. Dequantize output to float32
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


def q15_sat_sub(a, b):
    """Saturating Q15 subtraction."""
    result = int(a) - int(b)
    if result > 32767:
        return 32767
    elif result < -32768:
        return -32768
    return result


def load_ica_state(state_path):
    """Load ICA calibration state from .cortex_state file."""
    with open(state_path, 'rb') as f:
        header = f.read(16)
        if len(header) != 16:
            raise ValueError(f"Invalid state file: header too short ({len(header)} bytes)")

        magic, abi_version, state_version, state_size = struct.unpack('<IIII', header)
        if magic != 0x434F5254:
            raise ValueError(f"Invalid magic number: 0x{magic:08X}")

        payload = f.read(state_size)

    C = struct.unpack('<I', payload[:4])[0]
    offset = 4
    mean = np.frombuffer(payload[offset:offset + C * 4], dtype='<f4').copy()
    offset += C * 4
    W_unmix = np.frombuffer(payload[offset:offset + C * C * 4], dtype='<f4').reshape(C, C).copy()

    return {
        'mean': mean.astype(np.float32),
        'W_unmix': W_unmix.astype(np.float32),
        'C': C,
    }


def ica_q15_oracle(input_data, state):
    """
    Q15-aware ICA reference implementation.

    Args:
        input_data: Input array of shape (W, C), float32
        state: ICA state dict with 'mean' [C] and 'W_unmix' [C, C]

    Returns:
        output_data: Array of shape (W, C), float32 (dequantized Q15)
    """
    W, C = input_data.shape
    mean = state['mean']
    W_unmix = state['W_unmix']

    # Step 1: Quantize mean and unmixing matrix to Q15
    mean_q15 = float_to_q15(mean)
    W_unmix_q15 = float_to_q15(W_unmix)

    # Step 2: Quantize input to Q15
    q15_in = float_to_q15(input_data)

    # Step 3: Apply unmixing in integer arithmetic
    q15_out = np.zeros((W, C), dtype=np.int16)

    for t in range(W):
        for out_c in range(C):
            acc = np.int64(0)
            for in_c in range(C):
                centered = q15_sat_sub(int(q15_in[t, in_c]), int(mean_q15[in_c]))
                acc += np.int64(centered) * np.int64(W_unmix_q15[out_c, in_c])

            # Round-to-nearest
            acc += (1 << 14)
            result = int(acc >> 15)

            if result > 32767:
                result = 32767
            elif result < -32768:
                result = -32768

            q15_out[t, out_c] = np.int16(result)

    return q15_to_float(q15_out)


if __name__ == "__main__":
    # CLI test mode
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
            print("Error: --state argument required for ICA")
            sys.exit(1)

        x = np.fromfile(input_path, dtype=np.float32)
        if x.size != 160 * 64:
            print(f"Error: Expected 10240 floats (160x64), got {x.size}")
            sys.exit(1)
        x = x.reshape(160, 64)

        state = load_ica_state(state_path)
        y = ica_q15_oracle(x, state)

        y.astype(np.float32).tofile(output_path)
        print(f"[ica@q15] Processed: {x.shape} -> {y.shape}")
        sys.exit(0)

    # Self-test
    np.random.seed(42)
    W, C = 160, 64

    mean = np.random.randn(C).astype(np.float32) * 0.1
    W_unmix = np.random.randn(C, C).astype(np.float32) * 0.05
    state = {'mean': mean, 'W_unmix': W_unmix, 'C': C}

    x = np.random.randn(W, C).astype(np.float32) * 0.5

    y = ica_q15_oracle(x, state)

    assert y.shape == (W, C), f"Shape mismatch: {y.shape}"
    assert not np.any(np.isnan(y)), "Output contains NaNs"
    assert y.dtype == np.float32

    print(f"ICA Q15 Oracle Self-Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Output range: [{y.min():.6f}, {y.max():.6f}]")
    print("PASSED")
