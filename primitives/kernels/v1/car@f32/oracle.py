#!/usr/bin/env python3
"""
Common Average Reference (CAR) Oracle

Reference implementation for CAR kernel validation.
"""

import numpy as np


def car_ref(x):
    """
    Compute Common Average Reference.
    
    Args:
        x: Input array of shape (W, C) in µV (float32)
    
    Returns:
        Array of shape (W, C) in µV (float32) with channel means subtracted
    """
    m = np.nanmean(x, axis=1, keepdims=True)
    return (x - m).astype(np.float32)


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
                # Ignore state file for stateless kernels
                i += 2
            else:
                i += 1

        # Load input
        x = np.fromfile(input_path, dtype=np.float32)
        if x.size != 160 * 64:
            print(f"Error: Expected 10240 floats (160×64), got {x.size}")
            sys.exit(1)

        x = x.reshape(160, 64)

        # Apply CAR
        y = car_ref(x)

        # Write output
        y.astype(np.float32).tofile(output_path)
        sys.exit(0)

    # Example usage and test
    np.random.seed(42)
    W, C = 160, 64

    # Generate synthetic data
    x = np.random.randn(W, C).astype(np.float32) * 100  # µV scale

    # Apply CAR
    y = car_ref(x)

    # Validate: mean across channels should be ≈ 0
    mean_per_time = np.mean(y, axis=1)
    max_deviation = np.max(np.abs(mean_per_time))

    print(f"CAR Oracle Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Max deviation from zero mean: {max_deviation:.6f} µV")
    print(f"Test {'PASSED' if max_deviation < 1e-4 else 'FAILED'}")

