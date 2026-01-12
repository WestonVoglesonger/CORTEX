#!/usr/bin/env python3
"""
Oracle (reference implementation) for no-op kernel.

The oracle for an identity function is trivial: output = input.
This validates that the C implementation doesn't corrupt data.
"""

import numpy as np
from typing import Tuple


def noop_oracle(input_data: np.ndarray) -> np.ndarray:
    """
    No-op oracle: Identity function.

    Args:
        input_data: Input signal (W × C) where W=window_length, C=channels

    Returns:
        Output signal (W × C), identical to input
    """
    return input_data.copy()


def validate_noop(input_data: np.ndarray, output_data: np.ndarray,
                  rtol: float = 1e-7, atol: float = 1e-9) -> Tuple[bool, str]:
    """
    Validate no-op kernel output against oracle.

    Args:
        input_data: Input signal (W × C)
        output_data: Kernel output (W × C)
        rtol: Relative tolerance
        atol: Absolute tolerance

    Returns:
        (is_valid, message) tuple
    """
    expected = noop_oracle(input_data)

    if not np.allclose(output_data, expected, rtol=rtol, atol=atol):
        max_diff = np.max(np.abs(output_data - expected))
        return False, f"Output differs from input (max diff: {max_diff:.2e})"

    return True, "Output matches input (identity function verified)"


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description='No-op kernel oracle')
    parser.add_argument('--test', help='Input data file (binary float32)')
    parser.add_argument('--output', help='Output data file (binary float32)')
    parser.add_argument('--state', help='Calibration state file (unused for noop)')
    args = parser.parse_args()

    if args.test and args.output:
        # Validation mode: Read input, process, write output
        try:
            # Read input data as flat float32 array
            input_data = np.fromfile(args.test, dtype=np.float32)

            if len(input_data) == 0:
                print("Error: Empty input file", file=sys.stderr)
                sys.exit(1)

            # Run oracle (identity function - just copy)
            output_data = noop_oracle(input_data.reshape(-1))  # Keep as 1D

            # Write output
            output_data.astype(np.float32).tofile(args.output)
            sys.exit(0)
        except Exception as e:
            print(f"Oracle execution failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Self-test mode: Test oracle with random data
        W, C = 160, 64
        test_input = np.random.randn(W, C).astype(np.float32)

        # Run oracle
        test_output = noop_oracle(test_input)

        # Validate
        is_valid, message = validate_noop(test_input, test_output)
        print(f"Oracle test: {message}")
        print(f"Validation: {'PASS' if is_valid else 'FAIL'}")
