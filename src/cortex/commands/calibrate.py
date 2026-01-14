"""Calibrate trainable kernels command (ABI v3)"""
import subprocess
from pathlib import Path
import yaml


def _read_dataset_spec(dataset_path):
    """
    Read dataset spec.yaml if it exists.

    Returns dict with:
        - data_path: Path to .float32 file
        - channels: Number of channels (from spec)
        - sample_rate_hz: Sample rate (from spec)
        - window_length: Window length (from spec)
    """
    dataset_path = Path(dataset_path)

    # If it's a directory, look for spec.yaml
    if dataset_path.is_dir():
        spec_path = dataset_path / 'spec.yaml'
        if not spec_path.exists():
            raise ValueError(f"Dataset directory missing spec.yaml: {dataset_path}")

        with open(spec_path) as f:
            spec = yaml.safe_load(f)

        # Get data file path from recordings
        if 'recordings' not in spec or not spec['recordings']:
            raise ValueError(f"spec.yaml missing 'recordings' section")

        data_file = spec['recordings'][0].get('path', 'data.float32')
        data_path = dataset_path / data_file

        if not data_path.exists():
            raise ValueError(f"Data file not found: {data_path}")

        return {
            'data_path': data_path,
            'channels': spec['format']['channels'],
            'sample_rate_hz': spec['format']['sample_rate_hz'],
            'window_length': spec['format']['window_length']
        }

    # If it's a .float32 file directly, return minimal info
    elif dataset_path.suffix == '.float32':
        if not dataset_path.exists():
            raise ValueError(f"Dataset file not found: {dataset_path}")
        return {'data_path': dataset_path}

    else:
        raise ValueError(f"Invalid dataset: {dataset_path} (expected directory with spec.yaml or .float32 file)")


def _parse_label_pattern(pattern, num_windows):
    """
    Parse label pattern like '100x0,100x1' into comma-separated string.

    Args:
        pattern: Pattern like "100x0,100x1" (100 class-0, 100 class-1)
        num_windows: Expected total windows

    Returns:
        str: "0,0,0,...,1,1,1"

    Raises:
        ValueError: If pattern is malformed or count doesn't match windows
    """
    parts = pattern.split(',')
    labels = []
    total = 0

    for part in parts:
        part = part.strip()
        if 'x' not in part:
            raise ValueError(
                f"Invalid label pattern: '{part}' (expected format: '100x0')\n"
                f"  Example: '100x0,100x1' means 100 class-0 windows, 100 class-1 windows"
            )

        count_str, label_str = part.split('x', 1)
        try:
            count = int(count_str)
            label = int(label_str)
        except ValueError:
            raise ValueError(f"Invalid numbers in pattern '{part}' (expected 'NxM' where N, M are integers)")

        if count < 0:
            raise ValueError(f"Negative count in pattern '{part}' (count must be >= 0)")
        if label < 0:
            raise ValueError(f"Negative label in pattern '{part}' (label must be >= 0)")

        labels.extend([str(label)] * count)
        total += count

    if total != num_windows:
        raise ValueError(
            f"Label count mismatch: pattern specifies {total} windows, but --windows is {num_windows}\n"
            f"  Adjust pattern or --windows to match"
        )

    return ','.join(labels)


def setup_parser(parser):
    """Setup argument parser for calibrate command"""
    parser.add_argument(
        '--kernel',
        required=True,
        help='Kernel to calibrate (must support cortex_calibrate)'
    )
    parser.add_argument(
        '--dataset',
        required=True,
        help='Path to calibration dataset (directory with spec.yaml or .float32 file)'
    )
    parser.add_argument(
        '--windows',
        type=int,
        default=500,
        help='Number of windows to use for calibration (default: 500)'
    )
    parser.add_argument(
        '--output',
        required=True,
        help='Output path for calibration state file (.cortex_state)'
    )
    parser.add_argument(
        '--spec-uri',
        help='Plugin spec_uri (default: primitives/kernels/v1/{kernel}@f32)'
    )
    parser.add_argument(
        '--labels',
        help='Labels for CSP (pattern syntax: "100x0,100x1" = 100 class-0, 100 class-1)'
    )
    parser.add_argument(
        '--channels',
        type=int,
        help='Override channels from dataset spec (optional)'
    )
    parser.add_argument(
        '--window-length',
        type=int,
        help='Override window length from dataset spec (optional)'
    )
    parser.add_argument(
        '--sample-rate',
        type=float,
        help='Override sample rate from dataset spec (optional)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show verbose calibration output'
    )


def execute(args):
    """Execute calibrate command"""
    print("=" * 80)
    print("CORTEX Kernel Calibration (ABI v3)")
    print("=" * 80)

    # Read dataset spec
    try:
        spec = _read_dataset_spec(args.dataset)
    except ValueError as e:
        print(f"\n✗ Dataset error: {e}")
        return 1

    # Use spec values, allow CLI overrides
    channels = args.channels if args.channels is not None else spec.get('channels', 64)
    window_length = args.window_length if args.window_length is not None else spec.get('window_length', 160)
    sample_rate = args.sample_rate if args.sample_rate is not None else spec.get('sample_rate_hz', 160)

    # Parse labels if provided
    labels_str = None
    if args.labels:
        try:
            labels_str = _parse_label_pattern(args.labels, args.windows)
        except ValueError as e:
            print(f"\n✗ Label parsing error: {e}")
            return 1

    # Validate output path
    output_path = Path(args.output)
    if not args.output.endswith('.cortex_state'):
        print("\n✗ Output file must have .cortex_state extension")
        return 1

    # Check if calibration binary exists
    calib_binary = Path('sdk/kernel/tools/cortex_calibrate')
    if not calib_binary.exists():
        print("\n✗ Calibration binary not found: sdk/kernel/tools/cortex_calibrate")
        print("  This binary is part of the CORTEX SDK")
        print("  Run 'make all' to build it")
        return 1

    # Build spec_uri if not provided
    spec_uri = args.spec_uri or f"primitives/kernels/v1/{args.kernel}@f32"

    print(f"\nKernel:       {args.kernel}")
    print(f"Spec URI:     {spec_uri}")
    print(f"Dataset:      {args.dataset}")
    if spec.get('channels'):
        print(f"  (from spec: {spec['channels']}ch @ {spec['sample_rate_hz']}Hz, W={spec['window_length']})")
    print(f"Config:       C={channels}, W={window_length}, Fs={sample_rate}Hz")
    print(f"Windows:      {args.windows}")
    if labels_str:
        # Show abbreviated labels
        label_preview = labels_str if len(labels_str) < 60 else labels_str[:57] + "..."
        print(f"Labels:       {label_preview}")
    print(f"Output:       {args.output}")
    print()

    # Build command
    cmd = [
        str(calib_binary),
        '--plugin', spec_uri,
        '--dataset', str(spec['data_path']),
        '--windows', str(args.windows),
        '--channels', str(channels),
        '--window-length', str(window_length),
        '--sample-rate', str(int(sample_rate)),
        '--output', args.output
    ]

    if labels_str:
        cmd.extend(['--labels', labels_str])

    if args.verbose:
        cmd.append('--verbose')

    # Run calibration
    print("Running calibration...")
    result = subprocess.run(cmd, capture_output=not args.verbose, text=True)

    if result.returncode != 0:
        print("\n✗ Calibration failed")
        if not args.verbose:
            if result.stdout:
                print("\nStdout:")
                print(result.stdout)
            if result.stderr:
                print("\nStderr:")
                print(result.stderr)
        return 1

    # Verify output file was created
    if not output_path.exists():
        print("\n✗ Calibration completed but output file was not created")
        return 1

    # Show file size
    file_size = output_path.stat().st_size
    print(f"\n✓ Calibration successful")
    print(f"  State file: {args.output} ({file_size:,} bytes)")
    print("\nUsage:")
    print(f"  cortex run --kernel {args.kernel} --state {args.output}")
    print(f"  cortex validate --kernel {args.kernel} --calibration-state {args.output}")
    print("=" * 80)

    return 0
