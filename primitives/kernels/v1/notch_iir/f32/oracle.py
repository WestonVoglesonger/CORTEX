#!/usr/bin/env python3
"""
Notch IIR Filter Oracle

Reference implementation for notch IIR kernel validation.
"""

from scipy.signal import iirnotch, lfilter


def notch_ref(x, fs=160.0, f0=60.0, Q=30.0, zi=None):
    """
    Apply notch IIR filter with state management.

    Args:
        x: Input array of shape (W, C) in µV (float32)
        fs: Sampling rate (Hz). Default: 160.0
        f0: Notch frequency (Hz). Default: 60.0
        Q: Quality factor. Default: 30.0
        zi: Initial filter state. Shape (2, C). Must be provided.

    Returns:
        y: Filtered output of shape (W, C) in µV (float32)
        zf: Final filter state (for state persistence)
    """
    b, a = iirnotch(f0, Q, fs=fs)

    # Always provide zi (should be initialized to zeros if starting fresh)
    y, zf = lfilter(b, a, x, axis=0, zi=zi)

    return y.astype('float32'), zf


if __name__ == "__main__":
    import numpy as np
    import sys
    import os
    
    # CLI test mode
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        if len(sys.argv) < 3:
            print("Usage: python3 oracle.py --test <input_file> [--output <output_file>] [--state <state_file>]")
            sys.exit(1)

        input_path = sys.argv[2]
        # Default paths (backward compatible)
        output_path = "/tmp/test_output.bin"
        state_path = "/tmp/notch_state.npy"
        
        # Parse optional --output and --state arguments
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--output" and i + 1 < len(sys.argv):
                output_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--state" and i + 1 < len(sys.argv):
                state_path = sys.argv[i + 1]
                i += 2
            else:
                print(f"Warning: Unknown argument {sys.argv[i]}")
                i += 1

        # Load input data (interleaved: [sample0_ch0, sample0_ch1, ..., sample0_ch63, sample1_ch0, ...])
        x = np.fromfile(input_path, dtype=np.float32)
        # Reshape to (W, C) assuming W=160, C=64 for now
        # Data is already in correct format: samples×channels
        if x.size % 64 != 0:
            print(f"Error: Input size {x.size} not divisible by 64 channels")
            sys.exit(1)

        # Assume single window of 160 samples × 64 channels
        if x.size != 160 * 64:
            print(f"Error: Expected 10240 floats (160×64), got {x.size}")
            sys.exit(1)

        x = x.reshape(160, 64)

        # Load persistent state if it exists (stateful across windows)
        zi = np.zeros((2, 64))  # Always provide zi, initialize to zeros if no state
        if os.path.exists(state_path):
            zi = np.load(state_path)
            # zi should be (2, C) for biquad filter
            if zi.shape != (2, 64):
                zi = np.zeros((2, 64))  # Reset if wrong shape

        # Apply filter with persistent state
        y, zf = notch_ref(x, f0=60.0, Q=30.0, zi=zi)

        # Save state for next window
        np.save(state_path, zf)

        # Write output
        y.astype(np.float32).tofile(output_path)

        # Print info
        print(f"Processed {x.shape[0]} samples, {x.shape[1]} channels")
        sys.exit(0)
    
    # Example usage and test
    np.random.seed(42)
    W, C = 160, 64
    
    # Generate synthetic data: sine wave at 60 Hz + noise
    t = np.arange(W) / 160.0
    x = (
        np.sin(2 * np.pi * 60 * t)[:, None] * 10  # 60 Hz component
        + np.random.randn(W, C).astype(np.float32) * 5  # noise
    )
    
    # Apply notch filter
    y, zf = notch_ref(x, f0=60.0, Q=30.0)
    
    print(f"Notch IIR Oracle Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Filter state shape: {zf.shape if zf is not None else 'None'}")
    print(f"Notch at {60.0} Hz with Q={30.0}")
    print("60 Hz component should be attenuated")

