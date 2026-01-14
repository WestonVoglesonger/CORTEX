#!/usr/bin/env python3
"""
Oracle reference implementation for CSP kernel (ABI v3 trainable).

Uses NumPy/SciPy for Common Spatial Pattern (CSP) spatial filtering.
Implements CSP algorithm from scratch for motor imagery classification.

CSP Algorithm:
  1. Calibration: Compute class covariances C0, C1
  2. Solve generalized eigenvalue problem: C1 @ V = λ @ (C0 + C1) @ V
  3. Select top-m and bottom-m eigenvectors as spatial filters
  4. Inference: Project data to CSP space: y = W @ x.T

This maximizes variance ratio between two classes (e.g., left vs right hand motor imagery).
"""

import numpy as np
from scipy.linalg import eigh


def calibrate_csp(calibration_data, labels, n_components=4):
    """
    Train CSP spatial filters on two-class calibration data.

    Args:
        calibration_data: Shape (num_windows, W, C) float32 array
        labels: Shape (num_windows,) int array with class labels (0 or 1)
        n_components: Number of CSP components to extract (default: 4, must be even)

    Returns:
        state_dict: Dictionary with trained parameters
            - 'filters': Spatial filter matrix [n_components, C]
            - 'n_channels': Number of input channels
            - 'n_components': Number of output components
            - 'version': State version (for evolution tracking)
    """
    num_windows, W, C = calibration_data.shape

    # Validate labels
    unique_labels = np.unique(labels)
    if len(unique_labels) != 2:
        raise ValueError(f"CSP requires exactly 2 classes, got {len(unique_labels)}: {unique_labels}")

    # Map labels to 0 and 1
    label_0, label_1 = unique_labels
    mask_0 = (labels == label_0)
    mask_1 = (labels == label_1)

    # Split data by class
    data_class_0 = calibration_data[mask_0]  # Shape: (N0, W, C)
    data_class_1 = calibration_data[mask_1]  # Shape: (N1, W, C)

    n0, n1 = data_class_0.shape[0], data_class_1.shape[0]
    print(f"[oracle] Class 0: {n0} windows, Class 1: {n1} windows")

    # Compute covariance matrices for each class
    # C_k = (1/N_k) * sum_i(x_i @ x_i.T) where x_i is [C, W]

    def compute_covariance(data):
        """Compute average covariance matrix for a set of windows."""
        N, W, C = data.shape
        cov = np.zeros((C, C), dtype=np.float64)

        for i in range(N):
            x = data[i].T  # Shape: [C, W]
            # Handle NaNs
            x = np.nan_to_num(x, nan=0.0)
            # Compute covariance: x @ x.T / W
            cov += (x @ x.T) / W

        return cov / N

    C0 = compute_covariance(data_class_0)
    C1 = compute_covariance(data_class_1)

    # Regularize covariances (add small diagonal term for numerical stability)
    reg = 1e-6
    C0 += reg * np.eye(C)
    C1 += reg * np.eye(C)

    # Solve generalized eigenvalue problem: C1 @ V = λ @ (C0 + C1) @ V
    # Equivalent to: eigh(C1, C0 + C1)
    C_sum = C0 + C1

    try:
        eigenvalues, eigenvectors = eigh(C1, C_sum)
    except np.linalg.LinAlgError as e:
        print(f"[oracle] Eigenvalue decomposition failed: {e}")
        # Return identity as fallback
        fallback_filters = np.eye(n_components, C, dtype=np.float32)
        return {
            'filters': fallback_filters,
            'n_channels': C,
            'n_components': n_components,
            'version': 1
        }

    # Sort eigenvectors by eigenvalue (descending)
    idx = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    # Select spatial filters:
    # - Top m/2 eigenvectors (maximize class 1 variance)
    # - Bottom m/2 eigenvectors (maximize class 0 variance)
    m = n_components // 2
    top_indices = list(range(m))
    bottom_indices = list(range(C - m, C))
    selected_indices = top_indices + bottom_indices

    # Extract filters (each column is an eigenvector, we want rows)
    filters = eigenvectors[:, selected_indices].T  # Shape: [n_components, C]

    print(f"[oracle] Selected {n_components} CSP filters ({m} top + {m} bottom)")
    print(f"[oracle] Eigenvalue range: [{eigenvalues.min():.6f}, {eigenvalues.max():.6f}]")

    return {
        'filters': filters.astype(np.float32),
        'n_channels': C,
        'n_components': n_components,
        'version': 1
    }


def apply_csp(x, state):
    """
    Apply trained CSP spatial filters to single window.

    Args:
        x: Input window, shape (W, C) float32
        state: State dict from calibrate_csp()

    Returns:
        y: Output window, shape (W, n_components) float32 (CSP features)
    """
    filters = state['filters']  # [n_components, C]
    n_components, C = filters.shape
    W, C_in = x.shape

    assert C_in == C, f"Channel mismatch: state has {C}, input has {C_in}"

    # Handle NaNs (replace with 0)
    x_clean = np.nan_to_num(x, nan=0.0)

    # Apply spatial filters: y = x @ filters.T
    # x: [W, C], filters.T: [C, n_components] -> y: [W, n_components]
    y = x_clean @ filters.T

    return y.astype(np.float32)


def serialize_state_to_cortex_format(state):
    """
    Serialize CSP state to .cortex_state binary format.

    Format (little-endian):
      - n_channels (uint32): number of input channels
      - n_components (uint32): number of CSP components
      - filters (n_components × C × float32): spatial filters (column-major order)

    Returns:
        bytes: Serialized state payload
    """
    import struct

    n_channels = state['n_channels']
    n_components = state['n_components']
    filters = state['filters']  # [n_components, C]

    # Validate dimensions
    assert filters.shape == (n_components, n_channels), \
        f"Filter shape mismatch: {filters.shape} vs ({n_components}, {n_channels})"

    # Pack: n_channels (uint32) + n_components (uint32) + filters (column-major)
    payload = struct.pack('<II', n_channels, n_components)

    # Flatten in column-major (Fortran) order for C compatibility
    filters_bytes = filters.astype('<f4').flatten(order='F').tobytes()
    payload += filters_bytes

    return payload


def deserialize_state_from_cortex_format(payload):
    """
    Deserialize CSP state from .cortex_state binary format.

    Args:
        payload: bytes object with state data

    Returns:
        state_dict: Dictionary with 'filters', 'n_channels', 'n_components', 'version'
    """
    import struct

    # Read n_channels and n_components (2 × uint32)
    n_channels, n_components = struct.unpack('<II', payload[0:8])
    offset = 8

    # Read filters (n_components × C × float32) in column-major order
    filter_size = n_components * n_channels * 4
    filters_colmajor = np.frombuffer(payload[offset:offset + filter_size], dtype='<f4')

    # Reshape from column-major to row-major
    filters = filters_colmajor.reshape((n_components, n_channels), order='F')

    return {
        'filters': filters.astype(np.float32),
        'n_channels': n_channels,
        'n_components': n_components,
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
    """CLI interface for CSP oracle"""
    import sys

    # CLI calibration mode
    if len(sys.argv) > 1 and sys.argv[1] == "--calibrate":
        if len(sys.argv) < 3:
            print("Usage: python3 oracle.py --calibrate <calibration_data.float32> --windows <N> --labels <0,1,0,...> --output <state_file>")
            sys.exit(1)

        # Parse arguments
        calib_path = None
        num_windows = None
        labels_str = None
        output_path = None
        channels = 64
        window_length = 160
        sample_rate = 160

        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--calibration" and i + 1 < len(sys.argv):
                calib_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--calibrate" and i + 1 < len(sys.argv):
                calib_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--windows" and i + 1 < len(sys.argv):
                num_windows = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--labels" and i + 1 < len(sys.argv):
                labels_str = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--output" and i + 1 < len(sys.argv):
                output_path = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--channels" and i + 1 < len(sys.argv):
                channels = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--window_length" and i + 1 < len(sys.argv):
                window_length = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--sample_rate" and i + 1 < len(sys.argv):
                sample_rate = int(sys.argv[i + 1])
                i += 2
            else:
                calib_path = sys.argv[i] if calib_path is None else calib_path
                i += 1

        if not calib_path or not num_windows or not labels_str or not output_path:
            print("Error: Missing required arguments (need --calibration, --windows, --labels, --output)")
            sys.exit(1)

        # Parse labels (comma-separated)
        labels = np.array([int(l) for l in labels_str.split(',')])
        if len(labels) != num_windows:
            print(f"Error: Label count ({len(labels)}) doesn't match windows ({num_windows})")
            sys.exit(1)

        # Load calibration data
        calib_data = np.fromfile(calib_path, dtype=np.float32)

        # Reshape to (num_windows, W, C)
        W, C = window_length, channels
        expected_size = num_windows * W * C
        if calib_data.size < expected_size:
            print(f"Error: Calibration data too small (got {calib_data.size}, need {expected_size})")
            sys.exit(1)

        calib_data = calib_data[:expected_size].reshape(num_windows, W, C)

        # Train CSP
        print(f"[oracle] Training CSP on {num_windows} windows (classes: {np.unique(labels)})...")
        state = calibrate_csp(calib_data, labels, n_components=4)

        # Save state
        save_cortex_state(output_path, state)
        print(f"[oracle] Saved CSP state to {output_path}")
        print(f"         Filters shape: {state['filters'].shape}")
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

        # Apply CSP
        y = apply_csp(x, state)

        # Write output
        y.astype(np.float32).tofile(output_path)
        print(f"[oracle] Applied CSP: {x.shape} -> {y.shape}")
        sys.exit(0)

    # Standalone test mode (no arguments)
    print("=" * 80)
    print("CSP Oracle Test (ABI v3 Trainable Kernel)")
    print("=" * 80)

    # Generate synthetic two-class EEG data for motor imagery
    num_windows, W, C = 200, 160, 64  # 100 windows per class

    np.random.seed(42)

    # Create synthetic motor imagery data
    # Class 0: Left hand imagery (stronger alpha in left motor cortex)
    # Class 1: Right hand imagery (stronger alpha in right motor cortex)

    calibration_data = np.zeros((num_windows, W, C), dtype=np.float32)
    labels = np.zeros(num_windows, dtype=int)

    for i in range(num_windows):
        # Baseline EEG noise
        window = np.random.randn(W, C) * 10.0

        if i < num_windows // 2:
            # Class 0: Left hand (enhance channels 10-20)
            labels[i] = 0
            alpha_signal = np.sin(np.linspace(0, 10 * 2 * np.pi, W)) * 20.0
            window[:, 10:20] += alpha_signal[:, np.newaxis]
        else:
            # Class 1: Right hand (enhance channels 40-50)
            labels[i] = 1
            alpha_signal = np.sin(np.linspace(0, 10 * 2 * np.pi, W)) * 20.0
            window[:, 40:50] += alpha_signal[:, np.newaxis]

        calibration_data[i] = window

    print(f"\nCalibration data: {num_windows} windows × {W} samples × {C} channels")
    print(f"  Shape: {calibration_data.shape}")
    print(f"  Labels: {np.bincount(labels)} (class 0: {np.sum(labels == 0)}, class 1: {np.sum(labels == 1)})")
    print(f"  Data range: [{calibration_data.min():.2f}, {calibration_data.max():.2f}]")

    # Train CSP
    print("\nRunning CSP calibration...")
    state = calibrate_csp(calibration_data, labels, n_components=4)

    print(f"\n✓ Calibration successful")
    print(f"  Spatial filters: {state['filters'].shape}")
    print(f"  Input channels: {state['n_channels']}")
    print(f"  Output components: {state['n_components']}")
    print(f"  State version: {state['version']}")
    print(f"  Filter range: [{state['filters'].min():.6f}, {state['filters'].max():.6f}]")

    # Test on single window
    print("\nTesting inference on single window...")
    x_test = calibration_data[0]  # Use first window
    y_test = apply_csp(x_test, state)

    assert y_test.shape == (W, state['n_components']), f"Shape mismatch: {y_test.shape}"
    assert not np.any(np.isnan(y_test)), "Output contains NaNs"

    print(f"✓ Inference test passed")
    print(f"  Input:  {x_test.shape}, range [{x_test.min():.2f}, {x_test.max():.2f}]")
    print(f"  Output: {y_test.shape}, range [{y_test.min():.2f}, {y_test.max():.2f}]")

    # Test NaN handling
    print("\nTesting NaN handling...")
    x_nan = x_test.copy()
    x_nan[50:60, 10] = np.nan  # Inject NaNs
    y_nan = apply_csp(x_nan, state)
    assert not np.any(np.isnan(y_nan)), "NaN handling failed"
    print(f"✓ NaN handling passed")

    # Test serialization
    print("\nTesting state serialization...")
    payload = serialize_state_to_cortex_format(state)
    state_restored = deserialize_state_from_cortex_format(payload)

    assert np.allclose(state['filters'], state_restored['filters'], atol=1e-6), "Serialization failed"
    assert state['n_channels'] == state_restored['n_channels'], "Channel count mismatch"
    assert state['n_components'] == state_restored['n_components'], "Component count mismatch"
    print(f"✓ Serialization test passed ({len(payload)} bytes)")

    print("\n" + "=" * 80)
    print("All oracle tests passed!")
    print("=" * 80)


if __name__ == "__main__":
    main()
