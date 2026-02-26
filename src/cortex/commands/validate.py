"""Validate kernels against oracles command"""
import subprocess
import sys
from pathlib import Path

def setup_parser(parser):
    """Setup argument parser for validate command"""
    parser.add_argument(
        '--kernel',
        help='Validate specific kernel only'
    )
    parser.add_argument(
        '--calibration-state',
        help='Path to calibration state file (for trainable kernels)'
    )
    parser.add_argument(
        '--dtype',
        choices=['f32', 'float32', 'q15'],
        default='f32',
        help='Data type for validation (default: f32)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show verbose test output'
    )

def execute(args):
    """Execute validate command"""
    print("=" * 80)
    print("CORTEX Kernel Validation")
    print("=" * 80)

    # Check if test binary exists
    test_binary = Path('sdk/kernel/tools/cortex_validate')
    if not test_binary.exists():
        print("\n✗ Validation binary not found: sdk/kernel/tools/cortex_validate")
        print("  This binary is part of the CORTEX SDK")
        print("  Run 'make all' to build it")
        return 1

    if not args.kernel and args.dtype != 'f32':
        print(f"\nWarning: --dtype={args.dtype} ignored without --kernel (validate-all uses default dtype)")

    if args.kernel:
        dtype_display = args.dtype if args.dtype != 'float32' else 'f32'
        print(f"\nValidating kernel: {args.kernel} [dtype={dtype_display}]")
        cmd = [str(test_binary), '--kernel', args.kernel, '--windows', '10']
        if args.dtype in ('q15',):
            cmd.extend(['--dtype', args.dtype])
        if getattr(args, 'calibration_state', None):
            cmd.extend(['--state', args.calibration_state])
        if args.verbose:
            cmd.append('--verbose')
    else:
        print("\nValidating all kernels...")
        cmd = [str(test_binary)]

    # Run validation
    result = subprocess.run(cmd, capture_output=not args.verbose, text=True)

    if result.returncode != 0:
        print("\n✗ Validation failed")
        if not args.verbose and result.stderr:
            print("\nError output:")
            print(result.stderr)
        return 1

    print("\n✓ Validation passed")
    print("=" * 80)

    return 0
