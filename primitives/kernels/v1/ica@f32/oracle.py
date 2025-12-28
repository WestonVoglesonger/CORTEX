#!/usr/bin/env python3
"""
Oracle reference implementation for ICA kernel (ABI v3 trainable).

Uses sklearn's FastICA for offline batch training, then applies the learned
unmixing matrix to each window during inference.

ICA Algorithm:
  1. Calibration: Learn unmixing matrix W from batch data using FastICA
  2. Inference: Apply W to each window: y = x @ W.T

This removes artifacts (eye blinks, muscle activity) from EEG signals.
"""

import numpy as np
from sklearn.decomposition import FastICA

def calibrate_ica(calibration_data, n_components=None, max_iter=200, tol=1e-4, random_state=0):
    """
    Train ICA unmixing matrix on calibration data.

    Args:
        calibration_data: Shape (num_windows, W, C) float32 array
        n_components: Number of ICA components (default: C, extract all)
        max_iter: Maximum FastICA iterations
        tol: Convergence tolerance
        random_state: Random seed for reproducibility

    Returns:
        state_dict: Dictionary with trained parameters
            - 'W': Unmixing matrix [C, C] (components_ from FastICA)
            - 'mean': Channel means [C] for centering
            - 'version': State version (for evolution tracking)
    """
    num_windows, W, C = calibration_data.shape

    if n_components is None:
        n_components = C

    # Reshape to [num_windows*W, C] for batch training
    X = calibration_data.reshape(-1, C).astype(np.float64)  # Use float64 for training stability

    # Remove NaNs (replace with channel mean)
    for c in range(C):
        channel_data = X[:, c]
        if np.any(np.isnan(channel_data)):
            mean_val = np.nanmean(channel_data)
            channel_data[np.isnan(channel_data)] = mean_val if not np.isnan(mean_val) else 0.0
            X[:, c] = channel_data

    # Compute channel means for centering
    channel_means = np.mean(X, axis=0)

    # Run FastICA
    ica = FastICA(
        n_components=n_components,
        max_iter=max_iter,
        tol=tol,
        random_state=random_state,
        whiten='unit-variance',  # Whiten with unit variance
        fun='logcosh',  # Nonlinearity (similar to tanh)
        algorithm='parallel'  # Symmetric decorrelation
    )

    try:
        ica.fit(X)
    except Exception as e:
        print(f"[oracle] FastICA failed to converge: {e}")
        # Return identity matrix as fallback
        return {
            'W': np.eye(C, dtype=np.float32),
            'mean': channel_means.astype(np.float32),
            'version': 1
        }

    # Extract unmixing matrix (components in rows)
    # sklearn's components_ shape is [n_components, n_features]
    # We want [C, C] square matrix, so pad if needed
    W_unmix = np.zeros((C, C), dtype=np.float64)
    W_unmix[:n_components, :] = ica.components_

    # Fill remaining rows with zeros (or could use PCA directions)
    if n_components < C:
        # For unused components, use identity to preserve them
        for i in range(n_components, C):
            W_unmix[i, i] = 1.0

    return {
        'W': W_unmix.astype(np.float32),
        'mean': channel_means.astype(np.float32),
        'version': 1
    }

def apply_ica(x, state):
    """
    Apply trained ICA unmixing matrix to single window.

    Args:
        x: Input window, shape (W, C) float32
        state: State dict from calibrate_ica()

    Returns:
        y: Output window, shape (W, C) float32 (unmixed sources)
    """
    W_unmix = state['W']  # [C, C]
    mean = state['mean']  # [C]

    _, C = x.shape

    # Center data (subtract channel means from calibration)
    x_centered = x - mean[np.newaxis, :]

    # Handle NaNs (replace with 0 after centering)
    x_centered = np.nan_to_num(x_centered, nan=0.0)

    # Apply unmixing: y = x_centered @ W.T
    y = x_centered @ W_unmix.T

    return y.astype(np.float32)

def serialize_state_to_cortex_format(state):
    """
    Serialize ICA state to .cortex_state binary format.

    Format (little-endian):
      - C (uint32): number of channels
      - mean (C × float32): channel means
      - W (C × C × float32): unmixing matrix (row-major)

    Returns:
        bytes: Serialized state payload
    """
    import struct

    C = state['mean'].shape[0]
    mean = state['mean']  # [C]
    W = state['W']  # [C, C]

    # Pack: C (uint32) + mean (C×float32) + W (C×C×float32)
    payload = struct.pack('<I', C)  # Little-endian uint32
    payload += mean.astype('<f4').tobytes()  # Float32 little-endian
    payload += W.astype('<f4').tobytes()  # Row-major float32

    return payload

def deserialize_state_from_cortex_format(payload):
    """
    Deserialize ICA state from .cortex_state binary format.

    Args:
        payload: bytes object with state data

    Returns:
        state_dict: Dictionary with 'W', 'mean', 'version'
    """
    import struct

    # Read C (uint32)
    C = struct.unpack('<I', payload[0:4])[0]
    offset = 4

    # Read mean (C × float32)
    mean = np.frombuffer(payload[offset:offset + C*4], dtype='<f4')
    offset += C * 4

    # Read W (C × C × float32)
    W = np.frombuffer(payload[offset:offset + C*C*4], dtype='<f4').reshape(C, C)

    return {
        'W': W.astype(np.float32),
        'mean': mean.astype(np.float32),
        'version': 1
    }

def load_cortex_state(path):
    """Load .cortex_state file with 16-byte header validation"""
    import struct

    with open(path, 'rb') as f:
        # Read 16-byte header
        header = f.read(16)
        if len(header) != 16:
            raise ValueError(f"Invalid state file: header too short ({len(header)} bytes)")

        magic, abi_version, state_version, state_size = struct.unpack('<IIII', header)

        # Validate magic number
        if magic != 0x434F5254:  # "CORT"
            raise ValueError(f"Invalid magic number: 0x{magic:08X}")

        # Read payload
        payload = f.read(state_size)
        if len(payload) != state_size:
            raise ValueError(f"State payload size mismatch: got {len(payload)}, expected {state_size}")

    return deserialize_state_from_cortex_format(payload)

def save_cortex_state(path, state):
    """Save state to .cortex_state file with 16-byte header"""
    import struct

    payload = serialize_state_to_cortex_format(state)

    # Build 16-byte header
    magic = 0x434F5254  # "CORT"
    abi_version = 3
    state_version = state['version']
    state_size = len(payload)

    header = struct.pack('<IIII', magic, abi_version, state_version, state_size)

    with open(path, 'wb') as f:
        f.write(header)
        f.write(payload)

def main():
    """CLI interface for ICA oracle"""
    import sys

    # CLI calibration mode
    if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
        if len(sys.argv) < 3:
            print("Usage: python3 oracle.py --calibrate <calibration_data.float32> --windows <N> --output <state_file>")
            sys.exit(1)

        # Parse arguments
        calib_path = None
        num_windows = None
        output_path = None

        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--calibration" and i + 1 < len(sys.argv):
                calib_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--windows" and i + 1 < len(sys.argv):
                num_windows = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--output" and i + 1 < len(sys.argv):
                output_path = sys.argv[i + 1]
                i += 2
            else:
                calib_path = sys.argv[i] if calib_path is None else calib_path
                i += 1

        if not calib_path or not num_windows or not output_path:
            print("Error: Missing required arguments")
            sys.exit(1)

        # Load calibration data
        calib_data = np.fromfile(calib_path, dtype=np.float32)

        # Reshape to (num_windows, W, C)
        W, C = 160, 64
        expected_size = num_windows * W * C
        if calib_data.size < expected_size:
            print(f"Error: Calibration data too small (got {calib_data.size}, need {expected_size})")
            sys.exit(1)

        calib_data = calib_data[:expected_size].reshape(num_windows, W, C)

        # Train ICA
        print(f"[oracle] Training ICA on {num_windows} windows...")
        state = calibrate_ica(calib_data, max_iter=200, tol=1e-4)

        # Save state
        save_cortex_state(output_path, state)
        print(f"[oracle] Saved state to {output_path}")
        sys.exit(0)

    # CLI test mode (for validation)
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        if len(sys.argv) < 3:
            print("Usage: python3 oracle.py --test <input_file> --output <output_file> --state <state_file>")
            sys.exit(1)

        input_path = sys.argv[2]
        output_path = None
        state_path = None

        # Parse optional arguments
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

        if not output_path or not state_path:
            print("Error: Missing --output or --state argument")
            sys.exit(1)

        # Load input window
        x = np.fromfile(input_path, dtype=np.float32)
        if x.size != 160 * 64:
            print(f"Error: Expected 10240 floats (160×64), got {x.size}")
            sys.exit(1)

        x = x.reshape(160, 64)

        # Load state
        state = load_cortex_state(state_path)

        # Apply ICA
        y = apply_ica(x, state)

        # Write output
        y.astype(np.float32).tofile(output_path)
        sys.exit(0)

    # Standalone test mode (no arguments)
    print("=" * 80)
    print("ICA Oracle Test (ABI v3 Trainable Kernel)")
    print("=" * 80)

    # Generate synthetic calibration data
    num_windows, W, C = 100, 160, 64

    # Create mixed sources (simulate artifact-contaminated EEG)
    np.random.seed(42)

    # True sources: neural signals + artifacts
    calibration_data = np.random.randn(num_windows, W, C).astype(np.float32)

    # Add some structure (simulate eye blinks on first few channels)
    for w in range(num_windows):
        if np.random.rand() < 0.3:  # 30% of windows have blinks
            blink = np.sin(np.linspace(0, 2*np.pi, W)) * 50.0  # Large amplitude
            calibration_data[w, :, 0] += blink  # Affect channel 0 strongly
            calibration_data[w, :, 1] += blink * 0.5  # Affect channel 1 weakly

    print(f"\nCalibration data: {num_windows} windows × {W} samples × {C} channels")
    print(f"  Shape: {calibration_data.shape}")
    print(f"  Data range: [{calibration_data.min():.2f}, {calibration_data.max():.2f}]")

    # Train ICA
    print("\nRunning FastICA calibration...")
    state = calibrate_ica(calibration_data, max_iter=200, tol=1e-4)

    print(f"\n✓ Calibration successful")
    print(f"  Unmixing matrix: {state['W'].shape}")
    print(f"  Channel means: {state['mean'].shape}")
    print(f"  State version: {state['version']}")
    print(f"  W range: [{state['W'].min():.6f}, {state['W'].max():.6f}]")

    # Test on single window
    print("\nTesting inference on single window...")
    x_test = np.random.randn(W, C).astype(np.float32)
    y_test = apply_ica(x_test, state)

    assert y_test.shape == (W, C), f"Shape mismatch: {y_test.shape}"
    assert not np.any(np.isnan(y_test)), "Output contains NaNs"

    print(f"✓ Inference test passed")
    print(f"  Input:  {x_test.shape}, range [{x_test.min():.2f}, {x_test.max():.2f}]")
    print(f"  Output: {y_test.shape}, range [{y_test.min():.2f}, {y_test.max():.2f}]")

    # Test NaN handling
    print("\nTesting NaN handling...")
    x_nan = x_test.copy()
    x_nan[50:60, 10] = np.nan  # Inject NaNs
    y_nan = apply_ica(x_nan, state)
    assert not np.any(np.isnan(y_nan)), "NaN handling failed"
    print(f"✓ NaN handling passed")

    print("\n" + "=" * 80)
    print("All oracle tests passed!")
    print("=" * 80)

if __name__ == "__main__":
    main()
