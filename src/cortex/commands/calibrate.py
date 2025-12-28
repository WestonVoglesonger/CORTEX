"""Calibrate trainable kernels command (ABI v3)"""
import subprocess
import sys
from pathlib import Path

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
        help='Path to calibration dataset (.float32 file)'
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
        '--verbose', '-v',
        action='store_true',
        help='Show verbose calibration output'
    )

def execute(args):
    """Execute calibrate command"""
    print("=" * 80)
    print("CORTEX Kernel Calibration (ABI v3)")
    print("=" * 80)

    # Validate dataset file exists
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"\n✗ Dataset file not found: {args.dataset}")
        return 1

    # Validate output path
    output_path = Path(args.output)
    if not args.output.endswith('.cortex_state'):
        print("\n✗ Output file must have .cortex_state extension")
        return 1

    # Check if calibration binary exists
    calib_binary = Path('src/engine/harness/cortex_calibrate')
    if not calib_binary.exists():
        print("\n✗ Calibration binary not found: src/engine/harness/cortex_calibrate")
        print("  This binary is part of the ABI v3 harness implementation")
        print("  Run 'make all' to build it")
        return 1

    # Build spec_uri if not provided
    spec_uri = args.spec_uri or f"primitives/kernels/v1/{args.kernel}@f32"

    print(f"\nKernel:       {args.kernel}")
    print(f"Spec URI:     {spec_uri}")
    print(f"Dataset:      {args.dataset}")
    print(f"Windows:      {args.windows}")
    print(f"Output:       {args.output}")
    print()

    # Build command
    cmd = [
        str(calib_binary),
        '--plugin', spec_uri,
        '--dataset', args.dataset,
        '--windows', str(args.windows),
        '--output', args.output
    ]

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
    print(f"  cortex run --kernel {args.kernel} --calibration-state {args.output}")
    print(f"  cortex validate --kernel {args.kernel} --calibration-state {args.output}")
    print("=" * 80)

    return 0
