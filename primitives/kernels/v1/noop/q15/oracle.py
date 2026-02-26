#!/usr/bin/env python3
"""
Oracle (reference implementation) for noop@q15 kernel.

Q15 identity: quantize float32 input to Q15, copy, dequantize to float32.
The quantization round-trip introduces error bounded by 1/32768 per sample.
"""

import numpy as np
from typing import Tuple


def float_to_q15(x: np.ndarray) -> np.ndarray:
    """Convert float32 [-1.0, 1.0) to Q15 (int16)."""
    clamped = np.clip(x, -1.0, 1.0)
    return np.round(clamped * 32767.0).astype(np.int16)


def q15_to_float(x: np.ndarray) -> np.ndarray:
    """Convert Q15 (int16) back to float32."""
    return x.astype(np.float32) / 32768.0


def noop_q15_oracle(input_data: np.ndarray) -> np.ndarray:
    """
    Q15 no-op oracle: quantize → identity → dequantize.

    Args:
        input_data: Input signal as float32 (W*C elements)

    Returns:
        Output signal as float32 after Q15 round-trip
    """
    q15 = float_to_q15(input_data)
    return q15_to_float(q15)


def validate_noop_q15(input_data: np.ndarray, output_data: np.ndarray,
                      rtol: float = 1e-3, atol: float = 1e-3) -> Tuple[bool, str]:
    """
    Validate noop@q15 kernel output against oracle.

    Args:
        input_data: Original float32 input
        output_data: Kernel output (dequantized from Q15)
        rtol: Relative tolerance
        atol: Absolute tolerance

    Returns:
        (is_valid, message) tuple
    """
    expected = noop_q15_oracle(input_data)

    if not np.allclose(output_data, expected, rtol=rtol, atol=atol):
        max_diff = np.max(np.abs(output_data - expected))
        return False, f"Output differs from oracle (max diff: {max_diff:.2e})"

    return True, "Q15 identity function verified"


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='noop@q15 kernel oracle')
    parser.add_argument('--test', help='Input data file (binary float32)')
    parser.add_argument('--output', help='Output data file (binary float32)')
    parser.add_argument('--state', help='Calibration state file (unused for noop)')
    args = parser.parse_args()

    if args.test and args.output:
        try:
            input_data = np.fromfile(args.test, dtype=np.float32)

            if len(input_data) == 0:
                print("Error: Empty input file", file=sys.stderr)
                sys.exit(1)

            output_data = noop_q15_oracle(input_data)
            output_data.astype(np.float32).tofile(args.output)
            sys.exit(0)
        except Exception as e:
            print(f"Oracle execution failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Self-test mode
        W, C = 160, 64
        test_input = np.random.randn(W, C).astype(np.float32)
        test_input = np.clip(test_input * 0.1, -1.0, 1.0)  # Keep within Q15 range

        test_output = noop_q15_oracle(test_input)

        is_valid, message = validate_noop_q15(test_input, test_output)
        print(f"Oracle test: {message}")
        print(f"Validation: {'PASS' if is_valid else 'FAIL'}")

        # Verify quantization error is bounded
        max_error = np.max(np.abs(test_input - test_output))
        print(f"Max quantization error: {max_error:.6e} (bound: {1/32768:.6e})")
