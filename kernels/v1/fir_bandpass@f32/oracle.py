#!/usr/bin/env python3
"""
FIR Bandpass Filter Oracle

Reference implementation for FIR bandpass kernel validation.
"""

from scipy.signal import firwin, lfilter


def fir_bp_ref(x, fs=160.0, numtaps=129, zi=None):
    """
    Apply FIR bandpass filter with state management.
    
    Args:
        x: Input array of shape (W, C) in µV (float32)
        fs: Sampling rate (Hz). Default: 160.0
        numtaps: Number of filter taps. Default: 129
        zi: Initial filter state (tail). Shape (numtaps-1, C). Optional.
    
    Returns:
        y: Filtered output of shape (W, C) in µV (float32)
        zf: Final filter state (tail) for state persistence
        b: Filter coefficients
    """
    b = firwin(numtaps, [8, 30], pass_zero=False, fs=fs, window='hamming')
    
    # For FIR filters (a=[1.0]), lfilter doesn't use zi in the standard way
    # Instead, we manually prepend tail to input for continuous filtering
    # This matches the C implementation's approach
    
    if zi is not None:
        # Prepend tail to input for continuous filtering
        x_extended = np.vstack([zi, x])
        y_full = lfilter(b, [1.0], x_extended, axis=0)
        # Extract only the new window output (skip tail portion)
        y = y_full[zi.shape[0]:, :]
    else:
        y = lfilter(b, [1.0], x, axis=0)
    
    return y.astype('float32'), None, b


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
        state_path = "/tmp/fir_state.npy"
        
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
        if x.size % 64 != 0:
            print(f"Error: Input size {x.size} not divisible by 64 channels")
            sys.exit(1)

        # Assume single window of 160 samples × 64 channels
        if x.size != 160 * 64:
            print(f"Error: Expected 10240 floats (160×64), got {x.size}")
            sys.exit(1)

        x = x.reshape(160, 64)

        # Load persistent state if it exists (tail buffer for FIR)
        numtaps = 129
        zi = None
        if os.path.exists(state_path):
            zi_loaded = np.load(state_path)
            # zi should be (numtaps-1, C) = (128, 64) for FIR filter tail
            if zi_loaded.shape == (numtaps - 1, 64):
                zi = zi_loaded
            else:
                print(f"Warning: State shape {zi_loaded.shape} != expected {(numtaps-1, 64)}, ignoring")

        # Apply filter with persistent state
        # FIR filter tail is the last numtaps-1 INPUT samples (not output)
        # Prepend tail to input for continuous filtering
        if zi is not None:
            x_with_tail = np.vstack([zi, x])
        else:
            # First window: no tail, but pad with zeros for consistency
            x_with_tail = np.vstack([np.zeros((numtaps - 1, 64), dtype=np.float32), x])
        
        # Apply filter to extended input
        y_full, _, b = fir_bp_ref(x_with_tail, numtaps=numtaps, zi=None)
        
        # Extract only the new window output (skip tail portion)
        y = y_full[numtaps-1:, :]
        
        # Extract new tail: last numtaps-1 INPUT samples (for next window)
        zf = x[-numtaps+1:, :].copy()

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
    
    # Generate synthetic data: mix of frequencies
    t = np.arange(W) / 160.0
    x = (
        np.sin(2 * np.pi * 5 * t)[:, None] * 10    # 5 Hz (below passband)
        + np.sin(2 * np.pi * 10 * t)[:, None] * 20  # 10 Hz (in passband)
        + np.sin(2 * np.pi * 25 * t)[:, None] * 15  # 25 Hz (in passband)
        + np.random.randn(W, C).astype(np.float32) * 5  # noise
    )
    
    # Apply FIR bandpass filter
    y, zf, b = fir_bp_ref(x)
    
    print(f"FIR Bandpass Oracle Test")
    print(f"Input shape: {x.shape}")
    print(f"Output shape: {y.shape}")
    print(f"Filter taps: {len(b)}")
    print(f"Passband: 8-30 Hz")
    print("Components outside passband should be attenuated")

